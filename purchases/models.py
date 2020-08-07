from django.conf import settings
from django.db import models

from accountancy.models import (Contact, MatchedHeaders, TransactionHeader,
                                TransactionLine)
from items.models import Item
from vat.models import Vat


class Supplier(Contact):
    pass


class PurchaseHeader(TransactionHeader):
    no_analysis_required = [
        ('pbi', 'Brought Forward Invoice'),
        ('pbc', 'Brought Forward Credit Note'),
        ('pbp', 'Brought Forward Payment'),
        ('pbr', 'Brought Forward Refund'),
        ('pp', 'Payment'),
        ('pr', 'Refund'),
    ]
    analysis_required = [
        ('pi', 'Invoice'),
        ('pc', 'Credit Note'),
    ]
    no_lines_required = [
        ('pbp', 'Brought Forward Payment'),
        ('pbr', 'Brought Forward Refund'),
        ('pp', 'Payment'),
        ('pr', 'Refund'),
    ]
    lines_required = [
        ('pbi', 'Brought Forward Invoice'),
        ('pbc', 'Brought Forward Credit Note'),
        ('pi', 'Invoice'),
        ('pc', 'Credit Note'),
    ]
    credits = [
        'pbc',
        'pbp',
        'pp',
        'pc'
    ]
    debits = [
        'pbi',
        'pbr',
        'pr',
        'pi'
    ]
    payment_type = [
        'pbp',
        'pbr',
        'pp',
        'pr'
    ]
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    type_choices = no_analysis_required + analysis_required
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=type_choices
    )
    matched_to = models.ManyToManyField(
        'self', through='PurchaseMatching', symmetrical=False)


    def _create_payment_or_refund_nominal_transactions(self, nom_cls, nom_tran_cls, module, control_account_name, **kwargs):
        if self.total != 0:
            if control_account := kwargs.get("control_account"):
                pass
            else:
                try:
                    control_account = nom_cls.objects.get(
                        name=control_account_name)
                except nom_cls.DoesNotExist:
                    control_account = nom_cls.objects.get(
                        name=settings.DEFAULT_SYSTEM_SUSPENSE)
            nom_trans = []
            # create the bank entry first.  line = 1
            nom_trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk, # header field is PositiveInt field, not Foreign key
                    line="1",
                    nominal=self.cash_book.nominal,
                    value=self.total,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="t"
                )
            )
            # create the control account entry.  line = 2
            nom_trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk, # header field is PositiveInt field, not Foreign key
                    line="2",
                    nominal=control_account,
                    value= -1 * self.total,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="t"
                )
            )
            nom_tran_cls.objects.bulk_create(nom_trans)


    def create_nominal_transactions(self, nom_cls, nom_tran_cls, line_cls, module, control_account_name='', vat_nominal_name='', **kwargs):
        if self.type in ("pp", "pr"):
            self._create_payment_or_refund_nominal_transactions(
                nom_cls, nom_tran_cls, module, control_account_name, **kwargs
            )
        if self.type in ("pi", "pc"):
            self._create_invoice_or_credit_note_nominal_transactions(
                nom_cls, nom_tran_cls, line_cls, module, control_account_name, vat_nominal_name, **kwargs
            )

    
    def _edit_payment_or_refund_nominal_transactions(self, nom_cls, nom_tran_cls, module, control_account_name):
        nom_trans = nom_tran_cls.objects.filter(header=self.pk)
        try:
            control_account = nom_cls.objects.get(
                name=control_account_name)
        except nom_cls.DoesNotExist:
            control_account = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        if nom_trans and self.total != 0:
            # edit existing
            if nom_trans[0].line == 1:
                nom_trans[0].value = self.total
                nom_trans[0].nominal = self.cash_book.nominal # will hit the db again
                nom_trans[1].value = -1 * self.total
                nom_trans[1].nominal = control_account
            else:
                nom_trans[0].value = -1 * self.total
                nom_trans[0].nominal = control_account
                nom_trans[1].value = self.total
                nom_trans[1].nominal = self.cash_book.nominal # will hit the db again
            nom_tran_cls.objects.bulk_update(nom_trans, ["value", "nominal"])
        elif nom_trans and self.total == 0:
            nom_tran_cls.objects.filter(pk__in=[ t.pk for t in nom_trans ]).delete()
        elif not nom_trans and nom_trans != 0:
            # create nom trans
            nom_trans = self.create_nominal_transactions(nom_cls, nom_tran_cls, module, control_account=control_account)
            nom_tran_cls.objects.bulk_create(nom_trans)
        else:
            # do nothing is header is 0 and there are no trans
            return


    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, module, control_account_name):
        if self.type in ("pp", "pr"):
            self._edit_payment_or_refund_nominal_transactions(
                nom_cls, nom_tran_cls, module, control_account_name
            )


class PurchaseLineQuerySet(models.QuerySet):

    def line_bulk_update(self, instances):
        return self.bulk_update(
            instances,
            [
                "line_no",
                "description",
                "goods",
                "vat",
                "item",
                "nominal",
                "vat_code"
            ]
        )


class PurchaseLine(TransactionLine):
    header = models.ForeignKey(PurchaseHeader, on_delete=models.CASCADE)
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, null=True, blank=True)
    nominal = models.ForeignKey(
        'nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)
    vat_code = models.ForeignKey(
        Vat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_good_line")
    vat_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_vat_line")
    total_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_total_line")

    # It does not make sense that a line would exist without a nominal transaction but the purchase line is created
    # before the nominal transaction so it must do the create without the id for the nominal transaction

    objects = PurchaseLineQuerySet.as_manager()

    class Meta:
        ordering = ['line_no']


class PurchaseMatching(MatchedHeaders):
    # matched_by is the header record through which
    # all the other transactions were matched
    matched_by = models.ForeignKey(
        PurchaseHeader,
        on_delete=models.CASCADE,
        related_name="matched_by_these",
    )
    # matched_to is a header record belonging to
    # the set 'all the other transactions' described above
    matched_to = models.ForeignKey(
        PurchaseHeader,
        on_delete=models.CASCADE,
        related_name="matched_to_these"
    )

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

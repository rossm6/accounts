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


    def _create_payment_or_refund_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        if self.total != 0:
            if control_nominal := kwargs.get("control_nominal"):
                pass
            else:
                try:
                    control_nominal_name = kwargs.get('control_nominal_name')
                    control_nominal = nom_cls.objects.get(
                        name=control_nominal_name)
                except nom_cls.DoesNotExist:
                    control_nominal = nom_cls.objects.get(
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
                    nominal=control_nominal,
                    value= -1 * self.total,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="t"
                )
            )
            return nom_trans


    def _create_nominal_transactions_for_line(line, nom_tran_cls, module, vat_nominal, control_nominal):
        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=line.goods,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="g"
                )
            )
        if line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="v"
                )
            )
        if line.goods + line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk,
                    line=line.pk,
                    nominal=control_nominal,
                    value=-1 * (line.goods + line.vat),
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="t"
                )
            )   
        return trans   


    def _create_invoice_or_credit_note_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        if lines := not kwargs.get("lines"):
            return
        try:
            vat_nominal_name = kwargs.get('vat_nominal_name')
            vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            vat_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        try:
            control_nominal_name = kwargs.get('control_nominal_name')
            control_nominal = nom_cls.objects.get(
                name=control_nominal_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            control_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        nominal_transactions = []
        lines = kwargs.get('lines')
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                line, nom_tran_cls, module, vat_nominal, control_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls().objects.bulk_create(nominal_transactions)
            # FIX ME - THIS IS CRAZILY INEFFICIENT FOR A LARGE NUMBER OF LINES !!!!
            for line in lines:
                line_nominal_trans = {
                    nominal_transaction.field: nominal_transaction
                    for nominal_transaction in nominal_transactions
                    if nominal_transaction.line == line.pk
                }
                line.add_nominal_transactions(line_nominal_trans)
            line_cls.objects.bulk_update(lines, [
                'goods_nominal_transaction', 'vat_nominal_transaction', 'total_nominal_transaction'])


    def create_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        if self.type in ("pp", "pr"):
            self._create_payment_or_refund_nominal_transactions(
                nom_cls, nom_tran_cls, module, **kwargs
            )
        if self.type in ("pi", "pc"):
            self._create_invoice_or_credit_note_nominal_transactions(
                nom_cls, nom_tran_cls, module, **kwargs
            )

    
    def _edit_payment_or_refund_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        nom_trans = nom_tran_cls.objects.filter(header=self.pk)
        try:
            control_nominal_name = kwargs.get('control_nominal_name')
            control_nominal = nom_cls.objects.get(
                name=control_nominal_name)
        except nom_cls.DoesNotExist:
            control_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        if nom_trans and self.total != 0:
            # edit existing
            if nom_trans[0].line == 1:
                nom_trans[0].value = self.total
                nom_trans[0].nominal = self.cash_book.nominal # will hit the db again
                nom_trans[1].value = -1 * self.total
                nom_trans[1].nominal = control_nominal
            else:
                nom_trans[0].value = -1 * self.total
                nom_trans[0].nominal = control_nominal
                nom_trans[1].value = self.total
                nom_trans[1].nominal = self.cash_book.nominal # will hit the db again
            nom_tran_cls.objects.bulk_update(nom_trans, ["value", "nominal"])
        elif nom_trans and self.total == 0:
            nom_tran_cls.objects.filter(pk__in=[ t.pk for t in nom_trans ]).delete()
        elif not nom_trans and nom_trans != 0:
            # create nom trans
            if nom_trans := self._create_payment_or_refund_nominal_transactions(nom_cls, nom_tran_cls, module, control_nominal=control_nominal)
                nom_tran_cls.objects.bulk_create(nom_trans)
        else:
            # do nothing is header is 0 and there are no trans
            return


    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal, control_nominal):
        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = line.goods
            tran.ref = self.ref
            tran.period = self.period
            tran.date = self.date
            tran.type = self.type
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = line.vat
            tran.ref = self.ref
            tran.period = self.period
            tran.date = self.date
            tran.type = self.type
        if "t" in nom_trans:
            tran = nom_trans["t"]
            tran.nominal = control_nominal
            tran.value = -1 * (line.goods + line.vat)
            tran.ref = self.ref
            tran.period = self.period
            tran.date = self.date
            tran.type = self.type

        _nom_trans_to_update = []
        _nom_trans_to_delete = []

        if 'g' in nom_trans:
            if nom_trans["g"].value:
                _nom_trans_to_update.append(nominal_trans["g"])
            else:
                _nom_trans_to_delete.append(nominal_trans["g"])
                line.goods_nominal_transaction = None
        if 'v' in nom_trans:
            if nom_trans["v"].value:
                _nom_trans_to_update.append(nominal_trans["v"])
            else:
                _nom_trans_to_delete.append(nominal_trans["v"])
                line.vat_nominal_transaction = None
        if 't' in nom_trans:
            if nom_trans["t"].value:
                _nom_trans_to_update.append(nominal_trans["t"])
            else:
                _nom_trans_to_delete.append(nominal_trans["t"])
                line.total_nominal_transaction = None
        return _nom_trans_to_update, _nom_trans_to_delete


    def _edit_invoice_or_credit_note_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):

        lines_to_update = []
        new_nom_trans = []
        nom_trans_to_update = []
        nom_trans_to_delete = []

        try:
            vat_nominal_name = kwargs.get("vat_nominal_name")
            vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            vat_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)

        try:
            control_nominal_name = kwargs.get('control_nominal_name')
            control_nominal = nom_cls.objects.get(
                name=control_nominal_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            control_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)

        line_no = 1
        line_formset = kwargs.get('line_formset')
        lines_to_create_or_update_only = kwargs.get('lines_to_create_or_update_only')
        existing_nom_trans = kwargs.get('existing_nom_trans')

        for form in lines_to_create_or_update_only:
            if form.empty_permitted and form.has_changed():
                form.instance.header = self
                form.instance.line_no = line_no
                line_no = line_no + 1
                new_nom_trans += self._create_nominal_transactions_for_line(
                    nom_tran_cls, module, form.instance, vat_nominal, control_nominal
                )
            elif not form.empty_permitted:
                if form.instance.is_non_zero():
                    form.instance.line_no = line_no
                    line_no = line_no + 1
                    lines_to_update.append(form.instance)
                else:
                    line_formset.deleted_objects.append(form.instance)
                nominal_trans = {
                    tran.field: tran
                    for tran in existing_nom_trans
                    if tran.line == form.instance.pk
                }
                to_update, to_update = self._edit_nominal_transactions_for_line(
                    nominal_trans, form.instance, vat_nominal, control_nominal
                )
                nom_trans_to_update += to_update
                nom_trans_to_delete += to_delete


        for line in line_formset.deleted_objects:
            nominal_trans = [
                tran
                for tran in existing_nom_trans
                if tran.line == line.pk
            ]
            nom_trans_to_delete += nominal_trans

        line_cls = kwargs.get('line_cls')

        line_cls.objects.bulk_create(line_formset.new_objects)
        line_cls.objects.line_bulk_update(lines_to_update)
        line_cls.objects.filter(pk__in=[ line.pk for line in line_formset.deleted_objects ]).delete()
        nom_tran_cls.objects.bulk_create(new_nom_trans)
        nom_tran_cls.objects.line_bulk_update(nom_trans_to_update)
        nom_tran_cls.objects.filter(pk__in=[ nom_tran.pk for nom_trans in nom_trans_to_delete ]).delete()


    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):

        if self.type in ("pp", "pr"):
            self._edit_payment_or_refund_nominal_transactions(
                nom_cls, nom_tran_cls, module, **kwargs
            )
        if self.type in ("pbc", "pbi", "pc", "pi"):
            self._edit_invoice_or_credit_note_nominal_transactions(
                nom_cls, nom_tran_cls, module, **kwargs
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

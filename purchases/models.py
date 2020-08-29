from itertools import groupby

from django.conf import settings
from django.db import models

from accountancy.models import (Contact, MatchedHeaders, TransactionHeader,
                                TransactionLine)
from items.models import Item
from vat.models import Vat


class Supplier(Contact):
    pass


class PurchaseTransaction:

    def __init__(self, *args, **kwargs):
        self.module = "PL"
        self.header_obj = kwargs.get("header")

    def create_nominal_transactions(self, *args, **kwargs):
        return

    def edit_nominal_transactions(self, *args, **kwargs):
        return

class BroughtForwardInvoice(PurchaseTransaction):
    pass

class Invoice(PurchaseTransaction):

    def _create_nominal_transactions_for_line(self, line, nom_tran_cls, vat_nominal, control_nominal):
        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=line.goods,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="g"
                )
            )
        if line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="v"
                )
            )
        if line.goods + line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=control_nominal,
                    value=-1 * (line.goods + line.vat),
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
        return trans

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        if (vat_nominal := kwargs.get("vat_nominal")) is None:
            try:
                vat_nominal_name = kwargs.get('vat_nominal_name')
                vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                vat_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        if (control_nominal := kwargs.get("control_nominal")) is None:
            try:
                control_nominal_name = kwargs.get('control_nominal_name')
                control_nominal = nom_cls.objects.get(
                    name=control_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                control_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        nominal_transactions = []
        if lines := kwargs.get('lines'):
            lines = sorted(lines, key=lambda l: l.pk) # This might not be needed but i cannot find
        # anywhere in the Django docs mention of the necessary order of objects returned from bulk_create
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                line, nom_tran_cls, vat_nominal, control_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.bulk_create(
                nominal_transactions)
            nominal_transactions = sorted(nominal_transactions, key=lambda n: n.line)    
            line_key = lambda n: n.line
            nominal_transactions = sorted(nominal_transactions, key=line_key)
            for line, (key, line_nominal_trans) in zip(lines, groupby(nominal_transactions, line_key)):
                nom_tran_map = { tran.field : tran for tran in list(line_nominal_trans) }
                line.add_nominal_transactions(nom_tran_map)
            line_cls = kwargs.get('line_cls')
            line_cls.objects.bulk_update(lines, [
                'goods_nominal_transaction', 'vat_nominal_transaction', 'total_nominal_transaction'])


    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal, control_nominal):

        for tran_field, tran in nom_trans.items():
            tran.ref = self.header_obj.ref
            tran.period = self.header_obj.period
            tran.date = self.header_obj.date
            tran.type = self.header_obj.type

        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = line.goods
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = line.vat
        if "t" in nom_trans:
            tran = nom_trans["t"]
            tran.nominal = control_nominal
            tran.value = -1 * (line.goods + line.vat)

        _nom_trans_to_update = []
        _nom_trans_to_delete = []

        if 'g' in nom_trans:
            if nom_trans["g"].value:
                _nom_trans_to_update.append(nom_trans["g"])
            else:
                _nom_trans_to_delete.append(nom_trans["g"])
                line.goods_nominal_transaction = None
        if 'v' in nom_trans:
            if nom_trans["v"].value:
                _nom_trans_to_update.append(nom_trans["v"])
            else:
                _nom_trans_to_delete.append(nom_trans["v"])
                line.vat_nominal_transaction = None
        if 't' in nom_trans:
            if nom_trans["t"].value:
                _nom_trans_to_update.append(nom_trans["t"])
            else:
                _nom_trans_to_delete.append(nom_trans["t"])
                line.total_nominal_transaction = None
        return _nom_trans_to_update, _nom_trans_to_delete

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
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

        existing_nom_trans = kwargs.get('existing_nom_trans')
        existing_nom_trans = sorted(existing_nom_trans, key=lambda n: n.line)

        if new_lines := kwargs.get("new_lines"):
            sorted(new_lines, key=lambda l: l.pk)
        if updated_lines := kwargs.get("updated_lines"):
            sorted(updated_lines, key=lambda l: l.pk)
        if deleted_lines := kwargs.get("deleted_lines"):
            sorted(deleted_lines, key=lambda l: l.pk)

        if updated_lines:
            lines_to_update = [line.pk for line in updated_lines]
            nom_trans_to_update = [
                tran for tran in existing_nom_trans if tran.line in lines_to_update]
            nom_trans_to_update = sorted(nom_trans_to_update, key=lambda n: n.line)
            for line, (key, line_nominal_trans) in zip(updated_lines, groupby(nom_trans_to_update, key=lambda n: n.line)):
                nom_tran_map = { tran.field : tran for tran in list(line_nominal_trans) }
                to_update, to_delete = self._edit_nominal_transactions_for_line(
                    nom_tran_map, line, vat_nominal, control_nominal)
                nom_trans_to_update += to_update
                nom_trans_to_delete += to_delete

        if deleted_lines:
            lines_to_delete = [line.pk for line in deleted_lines]
            nom_trans_to_delete = [
                tran for tran in existing_nom_trans if tran.line in lines_to_delete]
            nom_trans_to_delete = sorted(
                nom_trans_to_delete, key=lambda n: n.line)
            for line, (key, nom_trans) in zip(deleted_lines, groupby(nom_trans_to_delete, key=lambda n: n.line)):
                nom_trans_to_delete += list(nom_trans)

        line_cls = kwargs.get('line_cls')
        # bulk_creates in this method
        self.create_nominal_transactions(
            nom_cls, nom_tran_cls,
            line_cls=line_cls,
            lines=new_lines,
            vat_nominal=vat_nominal,
            control_nominal=control_nominal
        )
        nom_tran_cls.objects.line_bulk_update(nom_trans_to_update)
        nom_tran_cls.objects.filter(
            pk__in=[nom_tran.pk for nom_tran in nom_trans_to_delete]).delete()


class BroughtForwardCreditNote(PurchaseTransaction):
    pass

class CreditNote(Invoice):
    pass

class Payment(PurchaseTransaction):

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        if self.header_obj.total != 0:
            if (control_nominal := kwargs.get("control_nominal")) is None:
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
                    module=self.module,
                    header=self.header_obj.pk,  # header field is PositiveInt field, not Foreign key
                    line="1",
                    nominal=self.header_obj.cash_book.nominal,
                    value=self.header_obj.total,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
            # create the control account entry.  line = 2
            nom_trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,  # header field is PositiveInt field, not Foreign key
                    line="2",
                    nominal=control_nominal,
                    value= -1 * self.header_obj.total,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
            return nom_tran_cls.objects.bulk_create(nom_trans)


    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        nom_trans = nom_tran_cls.objects.filter(
            header=self.header_obj.pk).order_by("line")
        try:
            control_nominal_name = kwargs.get('control_nominal_name')
            control_nominal = nom_cls.objects.get(
                name=control_nominal_name)
        except nom_cls.DoesNotExist:
            control_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        if nom_trans and self.header_obj.total != 0:
            bank_nom_tran, control_nom_tran = nom_trans
            bank_nom_tran.value = self.header_obj.total
            bank_nom_tran.nominal = self.header_obj.cash_book.nominal
            control_nom_tran.value = -1 * self.header_obj.total
            control_nom_tran.nominal = control_nominal
            nom_tran_cls.objects.bulk_update(nom_trans, ["value", "nominal"])
        elif nom_trans and self.header_obj.total == 0:
            nom_tran_cls.objects.filter(
                pk__in=[t.pk for t in nom_trans]).delete()
        elif not nom_trans and nom_trans != 0:
            # create nom trans
            self.create_nominal_transactions(
                nom_cls, nom_tran_cls, control_nominal=control_nominal)
        else:
            # do nothing as header is 0 and there are no trans
            return

class BroughtForwardPayment(PurchaseTransaction):
    pass

class Refund(Payment):
    pass

class BroughtForwardRefund(PurchaseTransaction):
    pass

class PurchaseHeader(TransactionHeader):
    # FIX ME - rename to "no_nominal_required"
    no_analysis_required = [
        ('pbi', 'Brought Forward Invoice'),
        ('pbc', 'Brought Forward Credit Note'),
        ('pbp', 'Brought Forward Payment'),
        ('pbr', 'Brought Forward Refund'),
    ]
    # FIX ME - rename to "nominals_required"
    analysis_required = [
        ("pp", "Payment"),
        ("pr", "Refund"),
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

    def get_type_transaction(self):
        if self.type == "pbi":
            return BroughtForwardInvoice(header=self)
        if self.type == "pbc":
            return BroughtForwardCreditNote(header=self)
        if self.type == "pbp":
            return BroughtForwardPayment(header=self)
        if self.type == "pbr":
            return BroughtForwardRefund(header=self)
        if self.type == "pi":
            return Invoice(header=self)
        if self.type == "pc":
            return CreditNote(header=self)
        if self.type == "pp":
            return Payment(header=self)
        if self.type == "pr":
            return Refund(header=self)

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

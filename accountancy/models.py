from itertools import groupby

from decimal import Decimal

from django.db import models


class Contact(models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.code

    class Meta:
        abstract = True


class Transaction:
    def __init__(self, *args, **kwargs):
        self.header_obj = kwargs.get("header")

    def create_nominal_transactions(self, *args, **kwargs):
        return

    def edit_nominal_transactions(self, *args, **kwargs):
        return


class InvoiceTransactionMixin:
    def _create_nominal_transactions_for_line(self, line, nom_tran_cls, vat_nominal, control_nominal):

        if self.header_obj.is_positive_type():
            if self.header_obj.is_debit_type():
                f = 1
            else:
                f = -1
        else:
            if self.header_obj.is_debit_type():
                f = -1
            else:
                f = 1

        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value= f * line.goods,
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
                    value= f * line.vat,
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
                    value=-1 * f * ( line.goods + line.vat),
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
            # This might not be needed but i cannot find
            lines = sorted(lines, key=lambda l: l.pk)
        # anywhere in the Django docs mention of the necessary order of objects returned from bulk_create
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                line, nom_tran_cls, vat_nominal, control_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.bulk_create(
                nominal_transactions)
            nominal_transactions = sorted(
                nominal_transactions, key=lambda n: n.line)

            def line_key(n): return n.line
            nominal_transactions = sorted(nominal_transactions, key=line_key)
            for line, (key, line_nominal_trans) in zip(lines, groupby(nominal_transactions, line_key)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
                line.add_nominal_transactions(nom_tran_map)
            line_cls = kwargs.get('line_cls')
            line_cls.objects.bulk_update(lines, [
                'goods_nominal_transaction', 'vat_nominal_transaction', 'total_nominal_transaction'])

    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal, control_nominal):

        if self.header_obj.is_positive_type():
            if self.header_obj.is_debit_type():
                f = 1
            else:
                f = -1
        else:
            if self.header_obj.is_debit_type():
                f = -1
            else:
                f = 1

        for tran_field, tran in nom_trans.items():
            tran.ref = self.header_obj.ref
            tran.period = self.header_obj.period
            tran.date = self.header_obj.date
            tran.type = self.header_obj.type

        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = f * line.goods
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = f * line.vat
        if "t" in nom_trans:
            tran = nom_trans["t"]
            tran.nominal = control_nominal
            tran.value = -1 * f * (line.goods + line.vat)

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
            nom_trans_to_update = sorted(
                nom_trans_to_update, key=lambda n: n.line)
            for line, (key, line_nominal_trans) in zip(updated_lines, groupby(nom_trans_to_update, key=lambda n: n.line)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
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


class PaymentTransactionMixin:
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
                    value=-1 * self.header_obj.total,
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


class DecimalBaseModel(models.Model):

    """
    The purpose of this class is simply to make sure the decimal zero is
    saved instead of null to the database.  At first i had 0.00 as the
    default value set against each field on the model but i don't like
    this showing as the initial value in the creation form.

    REMEMBER - clean is called as part of the full_clean process which
    itself it not called during save()
    """

    class Meta:
        abstract = True

    def clean(self):
        fields = self._meta.get_fields()
        for field in fields:
            if field.__class__ is models.fields.DecimalField:
                field_name = field.name
                field_value = getattr(self, field_name)
                if field_value == None:
                    setattr(self, field_name, Decimal(0.00))



class TransactionHeader(DecimalBaseModel):
    """

    Base transaction which can be sub classed.
    Subclasses will likely need to include a
    type property.  And a proxy model for each
    type which is a proxy of this transaction
    class.

    Examples below for sales ledger

    """
    statuses = [
        ("c", "cleared"),
        ("v", "void"),
    ]
    ref = models.CharField(max_length=20)
    goods = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    discount = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    total = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    paid = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    due = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    date = models.DateField()
    # payments do not require due dates
    due_date = models.DateField(null=True, blank=True)
    # example 202001, 202002.  This way we can sort easily.
    period = models.CharField(max_length=6)
    status = models.CharField(max_length=2, choices=statuses, default="c")

    class Meta:
        abstract = True

    def is_void(self):
        return self.status == "v"

    def is_negative_type(self):
        return self.type in self.negatives

    def is_positive_type(self):
        return self.type in self.positives

    def is_payment_type(self):
        return self.type in self.payment_type

    def is_credit_type(self):
        if self.type in self.credits:
            return True

    def is_debit_type(self):
        if self.type in self.debits:
            return True

    def will_have_nominal_transactions(self):
        return self.type in [ t[0] for t in self.analysis_required]

    @classmethod
    def get_types_requiring_analysis(cls):
        return [type[0] for type in cls.analysis_required]

    @classmethod
    def get_type_names_requiring_analysis(cls):
        return [type[1] for type in cls.analysis_required]

    @classmethod
    def get_types_requiring_lines(cls):
        return [type[0] for type in cls.lines_required]

    @classmethod
    def get_type_names_requiring_lines(cls):
        return [type[1] for type in cls.lines_required]

    @classmethod
    def get_debit_types(cls):
        return cls.debits

    @classmethod
    def get_credit_types(cls):
        return cls.credits


# class Invoice(TransactionHeader):
#     class Meta:
#         proxy = True


# class Receipt(TransactionHeader):
#     class Meta:
#         proxy = True


class TransactionLine(DecimalBaseModel):
    line_no = models.IntegerField()
    description = models.CharField(max_length=100)
    goods = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )

    class Meta:
        abstract = True

    def add_nominal_transactions(self, nominal_trans):
        if "g" in nominal_trans:
            self.goods_nominal_transaction = nominal_trans["g"]
        if "v" in nominal_trans:
            self.vat_nominal_transaction = nominal_trans["v"]
        if "t" in nominal_trans:
            self.total_nominal_transaction = nominal_trans["t"]


    def is_non_zero(self):
        if self.goods or self.vat:
            return True
        else:
            return False

class MatchedHeaders(models.Model):
    """
    Subclass must add the transaction_1 and transaction_2 foreign keys
    """
    # transaction_1 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="first_transaction")
    # transaction_2 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="second_transaction")
    created = models.DateField(auto_now_add=True)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )
    # example 202001, 202002.  This way we can sort easily.
    period = models.CharField(max_length=6)

    class Meta:
        abstract = True

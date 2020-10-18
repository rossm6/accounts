from datetime import date
from decimal import Decimal
from itertools import groupby

from django.conf import settings
from django.db import models
from django.db.models import Q
from simple_history.utils import (bulk_create_with_history,
                                  bulk_update_with_history)

from accountancy.descriptors import DecimalDescriptor, UIDecimalDescriptor
from accountancy.signals import audit_post_delete
from utils.helpers import (DELETED_HISTORY_TYPE, bulk_delete_with_history,
                           create_historical_records,
                           non_negative_zero_decimal)


class Contact(models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    email = models.EmailField()

    def __str__(self):
        return self.code

    class Meta:
        abstract = True


class AuditQuerySet(models.QuerySet):

    def audited_bulk_create(self, objs, batch_size=None, ignore_conflicts=False, user=None):
        return bulk_create_with_history(objs, self.model, batch_size=batch_size, default_user=user)

    def audited_bulk_update(self, objs, fields, batch_size=None, user=None):
        return bulk_update_with_history(objs, self.model, fields, batch_size=batch_size, default_user=user)

    def audited_bulk_line_update(self, objs, batch_size=None, user=None):
        return self.audited_bulk_update(
            objs,
            self.model.fields_to_update(),
            batch_size=batch_size,
            user=user
        )


class Audit:
    @classmethod
    def post_delete(cls, sender, instance, **kwargs):
        return create_historical_records([instance], instance._meta.model, DELETED_HISTORY_TYPE)

    def delete(self):
        audit_post_delete.send(sender=self._meta.model, instance=self)
        super().delete()


class Transaction:
    def __init__(self, *args, **kwargs):
        self.header_obj = kwargs.get("header")

    def create_nominal_transactions(self, *args, **kwargs):
        return

    def edit_nominal_transactions(self, *args, **kwargs):
        return

    def create_cash_book_entry(self, *args, **kwargs):
        return

    def edit_cash_book_entry(self, *args, **kwargs):
        return


class ControlAccountInvoiceTransactionMixin:
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
                    value=f * line.goods,
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
                    value=f * line.vat,
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
                    value=-1 * f * (line.goods + line.vat),
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
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                line, nom_tran_cls, vat_nominal, control_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.audited_bulk_create(
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
            line_cls.objects.audited_bulk_update(lines, [
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

        if (control_nominal := kwargs.get("control_nominal")) is None:
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
                nom_trans_to_delete += to_delete

        nom_trans_to_update = [
            tran for tran in nom_trans_to_update if tran not in nom_trans_to_delete]

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
        nom_tran_cls.objects.audited_bulk_line_update(nom_trans_to_update)
        bulk_delete_with_history(
            nom_trans_to_delete,
            nom_tran_cls,
        )


class CashBookEntryMixin:
    def create_cash_book_entry(self, cash_book_tran_cls, **kwargs):
        if self.header_obj.total != 0:
            return cash_book_tran_cls.objects.create(
                module=self.module,
                header=self.header_obj.pk,
                line=1,
                value=self.header_obj.total,
                ref=self.header_obj.ref,
                period=self.header_obj.period,
                date=self.header_obj.date,
                field="t",
                cash_book=self.header_obj.cash_book,
                type=self.header_obj.type
            )

    def edit_cash_book_entry(self, cash_book_tran_cls, **kwargs):
        try:
            cash_book_tran = cash_book_tran_cls.objects.get(
                module=self.module,
                header=self.header_obj.pk,
                line=1
            )
            if self.header_obj.total != 0:
                cash_book_tran.value = self.header_obj.total
                cash_book_tran.ref = self.header_obj.ref
                cash_book_tran.period = self.header_obj.period
                cash_book_tran.date = self.header_obj.date
                cash_book_tran.cash_book = self.header_obj.cash_book
                cash_book_tran.save()
            else:
                cash_book_tran.delete()
        except cash_book_tran_cls.DoesNotExist:
            if self.header_obj.total != 0:
                self.create_cash_book_entry(cash_book_tran_cls, **kwargs)


class CashBookPaymentTransactionMixin(CashBookEntryMixin, ControlAccountInvoiceTransactionMixin):
    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        kwargs["control_nominal"] = self.header_obj.cash_book.nominal
        return super().create_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        kwargs["control_nominal"] = self.header_obj.cash_book.nominal
        return super().edit_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)


class ControlAccountPaymentTransactionMixin:
    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        if self.header_obj.total != 0:

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
                    value=f * self.header_obj.total,
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
                    value=-1 * f * self.header_obj.total,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
            return nom_tran_cls.objects.audited_bulk_create(nom_trans)

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        nom_trans = nom_tran_cls.objects.filter(module=self.module,
                                                header=self.header_obj.pk).order_by("line")
        try:
            control_nominal_name = kwargs.get('control_nominal_name')
            control_nominal = nom_cls.objects.get(
                name=control_nominal_name)
        except nom_cls.DoesNotExist:
            control_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        if nom_trans and self.header_obj.total != 0:
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
            bank_nom_tran, control_nom_tran = nom_trans
            bank_nom_tran.value = f * self.header_obj.total
            bank_nom_tran.nominal = self.header_obj.cash_book.nominal
            control_nom_tran.value = -1 * f * self.header_obj.total
            control_nom_tran.nominal = control_nominal
            nom_tran_cls.objects.audited_bulk_update(
                nom_trans, ["value", "nominal"])
        elif nom_trans and self.header_obj.total == 0:
            bulk_delete_with_history(
                nom_trans,
                nom_tran_cls
            )
        elif not nom_trans and nom_trans != 0:
            # create nom trans
            self.create_nominal_transactions(
                nom_cls, nom_tran_cls, control_nominal=control_nominal)
        else:
            # do nothing as header is 0 and there are no trans
            return


class UIDecimalField(models.DecimalField):
    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)
        setattr(cls, self.name, DecimalDescriptor(self.name))
        setattr(cls, f"ui_{self.name}", UIDecimalDescriptor(self.name))


class TransactionBase:
    def is_negative_type(self):
        return self.type in self.negatives


class TransactionHeader(TransactionBase, models.Model, Audit):
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
    goods = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    discount = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    total = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    paid = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    due = UIDecimalField(
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

    objects = AuditQuerySet.as_manager()

    @staticmethod
    def ui_field_value(instance, field):
        value = getattr(instance, field)
        if instance.is_negative_type():
            ui_value = value * -1
        else:
            ui_value = value
        return non_negative_zero_decimal(ui_value)

    def ui_total(self):
        return self.ui_field_value(self, "total")

    def ui_paid(self):
        return self.ui_field_value(self, "paid")

    def ui_due(self):
        return self.ui_field_value(self, "due")

    def ui_status(self):
        if self.type == "nj":
            return ""
        if self.status == "c":
            if self.total == self.paid:
                return "fully matched"
            else:
                if self.due_date:
                    if self.due_date >= date.today():
                        return "outstanding"
                    else:
                        return "overdue"
                else:
                    return "not matched"
        elif self.is_void():
            return "Void"

    def is_void(self):
        return self.status == "v"

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

    def requires_analysis(self):
        if self.type in [t[0] for t in self.analysis_required]:
            return True

    def will_have_nominal_transactions(self):
        return self.type in [t[0] for t in self.analysis_required]

    def requires_lines(self):
        if self.type in [t[0] for t in self.lines_required]:
            return True

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


class TransactionLine(TransactionBase, models.Model, Audit):
    line_no = models.IntegerField()
    description = models.CharField(max_length=100)
    goods = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    # type field must be added to the subclass which has same choices as type field on header
    # this field is needed for UI presentation.  Without it we need to always remember to select_related
    # header for each line query which isn't ideal, or may be even, possible on occasion.

    class Meta:
        abstract = True

    objects = AuditQuerySet.as_manager()

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

    @staticmethod
    def ui_field_value(instance, field):
        """
        WARNING - this will hit the db each time it called
        if the line instance passed does not have the header
        already in memory.

        The calling code needs to select_related header
        therefore.
        """
        value = getattr(instance, field)
        if instance.header.is_negative_type():
            ui_value = value * -1
        else:
            ui_value = value
        return non_negative_zero_decimal(ui_value)

    def ui_total(self):
        return self.ui_field_value(self, "total")

    def ui_goods(self):
        return self.ui_field_value(self, "goods")

    def ui_vat(self):
        return self.ui_field_value(self, "vat")


class MatchedHeaders(models.Model, Audit):
    """
    Subclass must add the transaction_1 and transaction_2 foreign keys
    """
    # transaction_1 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="first_transaction")
    # transaction_2 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="second_transaction")
    created = models.DateField(auto_now_add=True)
    value = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )
    # example 202001, 202002.  This way we can sort easily.
    period = models.CharField(max_length=6)
    # type field must be added to the subclass which has same choices as type field on header
    # this field is needed for UI presentation.  Without it we need to always remember to select_related
    # header for each line query which isn't ideal, or may be even, possible on occasion.

    class Meta:
        abstract = True

    objects = AuditQuerySet.as_manager()

    @staticmethod
    def ui_match_value(transaction_header, match_value):
        """
        If the transaction_header is the matched_by in the match record,
        then match_value is the value of the value field in the same
        match record.  Else if matched_to is the transaction header
        in the same match record, then the match_value is the value of
        the value field in the match record multiplied by -1.
        """
        if transaction_header.is_negative_type():
            value = match_value * -1
        else:
            value = match_value
        return non_negative_zero_decimal(value)

    @classmethod
    def get_not_fully_matched_at_period(cls, headers, period):
        """
        To be called by the subclass so cls is the subclass
        """
        matches = (cls.objects
                   .filter(period__gt=period)
                   .filter(
                       Q(matched_by__in=headers) | Q(matched_to__in=headers)
                   ))

        matches_for_header = {}
        for match in matches:
            if match.matched_by_id not in matches_for_header:
                matches_for_header[match.matched_by_id] = []
            matches_for_header[match.matched_by_id].append(match)
            if match.matched_to_id not in matches_for_header:
                matches_for_header[match.matched_to_id] = []
            matches_for_header[match.matched_to_id].append(match)

        for header in headers:
            if header.pk in matches_for_header:
                for match in matches_for_header[header.pk]:
                    if match.matched_to == header:
                        header.due += match.value
                    else:
                        header.due -= match.value

        return [header for header in headers if header.due != 0]


class MultiLedgerTransactions(models.Model, Audit):
    module = models.CharField(max_length=3)  # e.g. 'PL' for purchase ledger
    # we don't bother with ForeignKeys to the header and line models
    # because this would require generic foreign keys which means extra overhead
    # in the SQL queries
    # and we only need the header and line number anyway to group within
    # the nominal transactions table
    header = models.PositiveIntegerField()
    # if a line transaction is created e.g. Purchase or Nominal Line, this will just be the primary key of the line record
    line = models.PositiveIntegerField()
    # but sometimes there won't be any lines e.g. a payment.  So the line will have to be set manually
    value = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    ref = models.CharField(max_length=100)  # CHECK LENGTH
    period = models.CharField(max_length=6)
    date = models.DateField()
    created = models.DateTimeField(auto_now=True)
    # User should never see this
    field_choices = [
        ('g', 'Goods'),
        ('v', 'Vat'),
        ('t', 'Total')
    ]
    field = models.CharField(max_length=2, choices=field_choices)
    # We had uniqueness set on the fields "module", "header" and "line"
    # but of course an analysis line can map to many different nominal transactions
    # at a minimum there is the goods and the vat on the analysis line
    # field is therefore a way of distinguishing the transactions and
    # guranteeing uniqueness

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'header', 'line', 'field'], name="unique_batch")
        ]

    objects = AuditQuerySet.as_manager()

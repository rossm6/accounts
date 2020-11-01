from datetime import date
from decimal import Decimal
from itertools import groupby

from django.conf import settings
from django.db import models
from django.db.models import Q
from simple_history.utils import (bulk_create_with_history,
                                  bulk_update_with_history)
from utils.helpers import non_negative_zero_decimal

from accountancy.descriptors import DecimalDescriptor, UIDecimalDescriptor
from accountancy.helpers import bulk_delete_with_history
from accountancy.mixins import AuditMixin


"""

    Two considerations -

        1. Move the methods on TransactionHeader which relate to transaction type to the TransactionBase model so that TransactionLine has them also
        2. MatchedHeaders would be improved by having two value fields.  One relating to the matched_by and the other to matched_to.  This should erase the logic
           in the calling code which checks what the value relates.

"""


class NonAuditQuerySet(models.QuerySet):

    def bulk_update(self, objs, batch_size=None):
        return super().bulk_update(objs, self.model.fields_to_update(), batch_size=batch_size)


class AuditQuerySet(models.QuerySet):
    """

    Provides wrappers for the bulk audit utilites provides by the simple_history package.
    Note we cannot include our own utility for deleting and auditing in bulk (at least not as easily)
    because bulk delete is not like bulk_create and bulk_delete in Django.

        E.g.

            SomeModel.objects.bulk_create([objects])

            SomeModel.objects.bulk_update([objects])

            SomeModel.objects.filter(pk__in=[o.pk for o in objects]).delete()

            # Django purposely provides bulk_delete differently to avoid accidentaly disasters !

    """

    def audited_bulk_create(self, objs, batch_size=None, ignore_conflicts=False, user=None):
        return bulk_create_with_history(objs, self.model, batch_size=batch_size, default_user=user)

    def audited_bulk_update(self, objs, fields=None, batch_size=None, user=None):
        if not fields:
            fields = self.model.fields_to_update()
        return bulk_update_with_history(objs, self.model, fields, batch_size=batch_size, default_user=user)


class Transaction:
    """
    This is not a model nor a model mixin.  Rather subclasses should encapsulate the
    business logic for a particular header based on a flag.

    For example take the PurchaseHeader model.  Like all header models it has a flag which
    indicates the type of header.  For PurchaseHeader this is either -

        pi  -   Purchase Invoice
        pc  -   Purchase Credit Note
        pp  -   Purchase Payment
        pr  -   Purchase Refund

    Each type of header should have a corresponding Transaction subclass which implements the business logic for
    this type of header.

    The transaction subclass for PurchaseHeader, type pp, would create nominal transactions one way;
    the transaction subclass for PurchaseHeader, type pi, would create nominal transactions another way.
    """

    # cls attributes
    module = None

    def __init__(self, *args, **kwargs):
        self.header_obj = kwargs.get("header")
        if not self.header_obj:
            raise ValueError("Transactions must have a header object")

    def __init_subclass__(cls):
        super().__init_subclass__()
        if cls.module not in settings.ACCOUNTANCY_MODULES.keys():
            raise ValueError("Transactions must have a module")

    @property
    def vat_type(self):
        if hasattr(self.header_obj, "vat_type"):
            return self.header_obj.vat_type
        return self._vat_type

    def create_nominal_transactions(self, *args, **kwargs):
        pass

    def create_vat_transactions(self, *args, **kwargs):
        pass

    def edit_nominal_transactions(self, *args, **kwargs):
        pass

    def edit_vat_transactions(self, *args, **kwargs):
        pass

    def create_cash_book_entry(self, *args, **kwargs):
        pass

    def edit_cash_book_entry(self, *args, **kwargs):
        pass


class AccountsDecimalField(models.DecimalField):
    """
    I want decimal fields in forms to show as blank by default.
    But I don't want the DB to save the value as null.

    This field will ensure a decimal of 0 is saved to the DB instead
    of null.
    """

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)
        setattr(cls, self.name, DecimalDescriptor(self.name))


class UIDecimalField(AccountsDecimalField):
    """
    This field includes a method which flips the sign of the value stored in DB
    so it looks right in the UI.
    """

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)
        setattr(cls, f"ui_{self.name}", UIDecimalDescriptor(self.name))


class TransactionBase:
    def is_negative_type(self):
        return self.type in self.negatives


class TransactionHeader(TransactionBase, models.Model, AuditMixin):
    """
    Every ledger which allows transactions to be posted must subclass this Abstract Model.
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
    created = models.DateTimeField(auto_now_add=True)

    types = None
    credits = None
    debits = None
    positives = None
    negatives = None
    analysis_required = None
    lines_required = None
    payment_types = None

    class Meta:
        abstract = True

    objects = AuditQuerySet.as_manager()

    def __init_subclass__(cls):
        super().__init_subclass__()
        if cls.types is None:
            raise ValueError(
                "Transaction headers must specify transaction types")
        if cls.credits is None:
            raise ValueError(
                "Transaction headers must specify the types which are credits.  If there are none define as an empty list."
                "  A credit transaction is one where a positive value would mean a negative entry in the nominal")
        if cls.debits is None:
            raise ValueError(
                "Transaction headers must specify the types which are debits.  If there are none define as an empty list."
                "  A debit transaction is one where a positive value would mean a positive entry in the nominal"
            )
        if cls.positives is None:
            raise ValueError(
                "Transaction headers must specify the types which should show as positives on account.  If there are none define as an empty list."
                "  E.g. an invoice is a positive transaction."
            )
        if cls.negatives is None:
            raise ValueError(
                "Transaction headers must specify the types which should show as negatives on account.  If there are none define as an empty list."
                "  E.g. a payment is a negative transaction."
            )
        if cls.analysis_required is None:
            raise ValueError(
                "Transaction headers must specify the types which require nominal analysis by the user.  If there are none define as an empty list."
                "  E.g. an invoice requires nominal analysis.  A brought invoice invoice does not."
            )
        if cls.lines_required is None:
            raise ValueError(
                "Transaction headers must specify the types which require lines be shown in the UI.  If there are none define as an empty list."
                "  E.g. an invoice requires lines.  A payment does not."
            )
        if cls.payment_types is None:
            raise ValueError(
                "Transaction headers must specify the types which are payment types i.e. will update the cashbook.  If there are none define as an empty list."
            )

    def get_nominal_transaction_factor(self):
        """

            A nominal cr is a negative value, a nominal debit is a positive value

            E.g. PL invoice for 120.00, goods 100.00 and vat 20.00

                Goods nominal should be updated with 100.00

            E.g. PL credit for 120.00, goods 100.00 and vat 20.00 

                Goods nominal should be updated with -100.00

            E.g. SL invoice for 120.00, goods 100.00 and vat 20.00

                Goods nominal should be updated with 100.00

            E.g. SL credit for 120.00, goods 100.00 and vat 20.00

                Goods nominal should be updated with 100.00

        """
        return (1 if self.is_positive_type() else -1) * (1 if self.is_debit_type() else -1)

    def ui_status(self):
        if self.type in ("nj", "cp", "cr", "cbr", "cbp"):
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
                    return "not fully matched"
        elif self.is_void():
            return "void"

    def is_void(self):
        return self.status == "v"

    def is_positive_type(self):
        if self.type in self.positives:
            return True
        return False

    def is_payment_type(self):
        return self.type in self.payment_types

    def is_credit_type(self):
        if self.type in self.credits:
            return True
        return False

    def is_debit_type(self):
        if self.type in self.debits:
            return True
        return False

    def requires_analysis(self):
        if self.type in [t[0] for t in self.analysis_required]:
            return True

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


class TransactionLine(TransactionBase, models.Model, AuditMixin):
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
    # this field is needed for the UI.  Without it we need to always remember to select_related
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


class MatchedHeaders(models.Model, AuditMixin):
    """
    Subclass must add the transaction_1 and transaction_2 foreign keys
    """
    # transaction_1 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="first_transaction")
    # transaction_2 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="second_transaction")
    created = models.DateField(auto_now_add=True)
    value = AccountsDecimalField(
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


class MultiLedgerTransactions(models.Model):
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

    objects = NonAuditQuerySet.as_manager()

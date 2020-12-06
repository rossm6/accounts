from datetime import date
from decimal import Decimal
from itertools import groupby

from django.conf import settings
from django.db import models
from django.db.models import Q
from controls.models import Period
from simple_history.utils import (bulk_create_with_history,
                                  bulk_update_with_history)

from accountancy.fields import AccountsDecimalField, UIDecimalField
from accountancy.helpers import (bulk_delete_with_history,
                                 non_negative_zero_decimal)
from accountancy.mixins import AuditMixin

"""

    Two considerations -

        1. Move the methods on TransactionHeader which relate to transaction type to the TransactionBase model so that TransactionLine has them also
        2. MatchedHeaders would be improved by having two value fields.  One relating to the matched_by and the other to matched_to.  This should erase the logic
           in the calling code which checks what the value relates.
        3. We have not tested AccountsDecimalField.

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


class TransactionBase:
    def is_negative_type(self):
        return self.type in self.negatives


class TransactionHeader(AuditMixin, TransactionBase, models.Model):
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
    period = models.ForeignKey(Period, on_delete=models.SET_NULL, null=True)
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


class TransactionLine(AuditMixin, TransactionBase, models.Model):
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


class MatchedHeaders(AuditMixin, models.Model):
    """
    Subclass must add the transaction_1 and transaction_2 foreign keys

    This is the most confusing part of the software so here goes ...

    This model represents the link between two transactions (e.g PL header or SL header)

    E.g.

    A payment of 120.00 is matched to an invoice for 120.00

    If the invoice was on the system already and the payment was being created / edited when the match 
    was created then -

    matched_by is the payment
    matched_to is the invoice

    matched_by is ALWAYS the transaction being created or edited

    value is the amount that is paid by matched_to.  It is the amount that was deducted from the outstanding
    value of the matched_to header, and the amount added to the paid value of the matched_to header, when the match
    was created.

    So for the same example

    matched_by = payment
    matched_to = invoice
    value = 120

    Thus, invoice outstanding and paid now both equal 0

    This is example is the most basic.

    There are other kinds of matching though which look a bit odd.

    E.g.

    A refund (1r) for 120.01 is created
    A payment (1p) for 120.00 is created
    
    Then, a refund (2r) for -0.01 is created and the two above trans are matched.

    Two match records are therefore created.

    1.
        matched_by = refund (2r)
        matched_to = payment (1p)
        value = -120 *

        * this is -120 because a payment is saved to the db as -120 total.  Only in the UI
          does it show as 120.00

    2. 

        matched_by = refund (2r)
        matched_to = refund (1r)
        value = 120


    This is sound.  Indeed all of the three transactions are now fully matched / paid i.e. none are
    outstanding.

    If we looked at the refund (2r) through the browser we'd see the following -

        match 1 -> payment of 120.00 -> match value -> +120.00
        match 2 > refund of 120.01 -> match value -> +120.01

    This is clear enough.

    Admittedly though from certain views it may seem a bit confusing.

    If we looekd at the payment (1p) through the browser we'd see -

        match 1 -> refund (2r) of -0.01 -> match value -> -120.00

    It has to be this way given the rules defined at the start but it may look a bit odd.

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
    period = models.ForeignKey(Period, on_delete=models.SET_NULL, null=True)
    # type field must be added to the subclass which has same choices as type field on header
    # this field is needed for UI presentation.  Without it we need to always remember to select_related
    # header for each line query which isn't ideal, or may be even, possible on occasion.

    class Meta:
        abstract = True

    objects = AuditQuerySet.as_manager()

    @staticmethod
    def show_match_in_UI(tran_being_being_edited_or_created=None, match=None):
        if not match:
            return None
        if tran_being_being_edited_or_created.pk == match.matched_to_id:
            header = match.matched_by
            value = MatchedHeaders.ui_match_value(header, -1 * match.value)
        else:
            header = match.matched_to
            value = MatchedHeaders.ui_match_value(header, match.value)
        return {
            "type": header.type,
            "ref": header.ref,
            "total": header.ui_total,
            "paid": header.ui_paid,
            "due": header.ui_due,
            "value": value
        }

    @staticmethod
    def ui_match_value(transaction_header, match_value):
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
    period = models.ForeignKey(Period, on_delete=models.SET_NULL, null=True)
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

    def update_details_from_header(self, header):
        self.ref = header.ref
        self.period = header.period
        self.date = header.date

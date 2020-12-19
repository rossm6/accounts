from uuid import uuid4

from accountancy.mixins import (CashBookEntryMixin,
                                ControlAccountInvoiceTransactionMixin,
                                ControlAccountPaymentTransactionMixin,
                                VatTransactionMixin)
from accountancy.models import (MatchedHeaders, Transaction, TransactionHeader,
                                TransactionLine)
from contacts.models import Contact
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.shortcuts import reverse
from simple_history import register
from vat.models import Vat


class Supplier(Contact):
    """
    Do not create or update via the Supplier model because it does
    not audit records.  Always use the Contact model instead.
    """
    class Meta:
        proxy = True

    @classmethod
    def simple_history_custom_set_up(cls):
        pass
        # without this it will try to register the Supplier class which is unwanted


class PurchaseTransaction(Transaction):
    module = "PL"
    _vat_type = "i"


class BroughtForwardInvoice(PurchaseTransaction):
    pass


class Invoice(VatTransactionMixin, ControlAccountInvoiceTransactionMixin, PurchaseTransaction):
    pass


class BroughtForwardCreditNote(PurchaseTransaction):
    pass


class CreditNote(Invoice):
    pass


class Payment(CashBookEntryMixin, ControlAccountPaymentTransactionMixin, PurchaseTransaction):
    pass


class BroughtForwardPayment(PurchaseTransaction):
    pass


class Refund(Payment):
    pass


class BroughtForwardRefund(PurchaseTransaction):
    pass


class ModuleTransactions:
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
    negatives = [
        'pbc',
        'pbp',
        'pp',
        'pc'
    ]
    positives = [
        'pbi',
        'pbr',
        'pr',
        'pi'
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
    payment_types = [
        'pbp',
        'pbr',
        'pp',
        'pr'
    ]
    types = no_analysis_required + analysis_required


class PurchaseHeader(ModuleTransactions, TransactionHeader):
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=ModuleTransactions.types
    )
    matched_to = models.ManyToManyField(
        'self', through='PurchaseMatching', symmetrical=False)

    class Meta:
        permissions = [
            # enquiry perms
            ("view_transactions_enquiry", "Can view transactions"),
            # report perms
            ("view_age_creditors_report", "Can view aged creditors report"),
            # transaction perms
            ("create_brought_forward_invoice_transaction",
             "Can create brought forward invoice"),
            ("create_brought_forward_credit_note_transaction",
             "Can create brought forward credit note"),
            ("create_brought_forward_payment_transaction",
             "Can create brought forward payment"),
            ("create_brought_forward_refund_transaction", "Can create brought forward refund"),
            ("create_invoice_transaction", "Can create invoice"),
            ("create_credit_note_transaction", "Can create credit note"),
            ("create_payment_transaction", "Can create payment"),
            ("create_refund_transaction", "Can create refund"),
            ("edit_brought_forward_invoice_transaction", "Can edit brought forward invoice"),
            ("edit_brought_forward_credit_note_transaction",
             "Can edit brought forward credit note"),
            ("edit_brought_forward_payment_transaction", "Can edit brought forward payment"),
            ("edit_brought_forward_refund_transaction", "Can edit brought forward refund"),
            ("edit_invoice_transaction", "Can edit invoice"),
            ("edit_credit_note_transaction", "Can edit credit note"),
            ("edit_payment_transaction", "Can edit payment"),
            ("edit_refund_transaction", "Can edit refund"),
            ("view_brought_forward_invoice_transaction", "Can view brought forward invoice"),
            ("view_brought_forward_credit_note_transaction",
             "Can view brought forward credit note"),
            ("view_brought_forward_payment_transaction", "Can view brought forward payment"),
            ("view_brought_forward_refund_transaction", "Can view brought forward refund"),
            ("view_invoice_transaction", "Can view invoice"),
            ("view_credit_note_transaction", "Can view credit note"),
            ("view_payment_transaction", "Can view payment"),
            ("view_refund_transaction", "Can view refund"),
            ("void_brought_forward_invoice_transaction", "Can void brought forward invoice"),
            ("void_brought_forward_credit_note_transaction",
             "Can void brought forward credit note"),
            ("void_brought_forward_payment_transaction", "Can void brought forward payment"),
            ("void_brought_forward_refund_transaction", "Can void brought forward refund"),
            ("void_invoice_transaction", "Can void invoice"),
            ("void_credit_note_transaction", "Can void credit note"),
            ("void_payment_transaction", "Can void payment"),
            ("void_refund_transaction", "Can void refund"),
        ]

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

    def get_absolute_url(self):
        return reverse("purchases:view", kwargs={"pk": self.pk})

class PurchaseLine(ModuleTransactions, TransactionLine):
    header = models.ForeignKey(PurchaseHeader, on_delete=models.CASCADE)
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
    vat_transaction = models.ForeignKey(
        'vat.VatTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_line_vat_transaction")
    type = models.CharField(
        max_length=3,
        choices=PurchaseHeader.types
        # see note on parent class for more info
    )

    # It does not make sense that a line would exist without a nominal transaction but the purchase line is created
    # before the nominal transaction so it must do the create without the id for the nominal transaction

    class Meta:
        ordering = ['line_no']

    @classmethod
    def fields_to_update(cls):
        return [
            "line_no",
            "description",
            "goods",
            "vat",
            "nominal",
            "vat_code",
            "type"
        ]


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
    matched_by_type = models.CharField(
        max_length=3,
        choices=PurchaseHeader.types
        # see note on parent class for more info
    )
    matched_to_type = models.CharField(
        max_length=3,
        choices=PurchaseHeader.types
        # see note on parent class for more info
    )
    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

    @classmethod
    def get_not_fully_matched_at_period(cls, headers, period):
        return super(PurchaseMatching, cls).get_not_fully_matched_at_period(headers, period)

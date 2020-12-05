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
from django.shortcuts import reverse
from simple_history import register
from vat.models import Vat


class Customer(Contact):
    """
    Do not create or update via the Customer model because it does
    not audit records.  Always use the Contact model instead.
    """
    class Meta:
        proxy = True

    @classmethod
    def simple_history_custom_set_up(cls):
        pass
        # without this it will try to register the Supplier class which is unwanted


class SalesTransaction(Transaction):
    module = "SL"
    _vat_type = "o"


class BroughtForwardInvoice(SalesTransaction):
    pass


class Invoice(VatTransactionMixin, ControlAccountInvoiceTransactionMixin, SalesTransaction):
    pass


class BroughtForwardCreditNote(SalesTransaction):
    pass


class CreditNote(Invoice):
    pass


class Receipt(CashBookEntryMixin, ControlAccountPaymentTransactionMixin, SalesTransaction):
    pass


class BroughtForwardReceipt(SalesTransaction):
    pass


class Refund(Receipt):
    pass


class BroughtForwardRefund(SalesTransaction):
    pass


class ModuleTransactionBase:
    # FIX ME - rename to "no_nominal_required"
    no_analysis_required = [
        ('sbi', 'Brought Forward Invoice'),
        ('sbc', 'Brought Forward Credit Note'),
        ('sbp', 'Brought Forward Receipt'),  # sbp = Sales B/F payment
        ('sbr', 'Brought Forward Refund'),
    ]
    # FIX ME - rename to "nominals_required"
    analysis_required = [
        ("sp", "Receipt"),
        ("sr", "Refund"),
        ('si', 'Invoice'),
        ('sc', 'Credit Note'),
    ]
    no_lines_required = [
        ('sbp', 'Brought Forward Receipt'),
        ('sbr', 'Brought Forward Refund'),
        ('sp', 'Receipt'),
        ('sr', 'Refund'),
    ]
    lines_required = [
        ('sbi', 'Brought Forward Invoice'),
        ('sbc', 'Brought Forward Credit Note'),
        ('si', 'Invoice'),
        ('sc', 'Credit Note'),
    ]
    negatives = [
        'sbc',
        'sbp',
        'sp',
        'sc'
    ]
    positives = [
        'sbi',
        'sbr',
        'sr',
        'si'
    ]
    credits = [
        'sbi',
        'sbr',
        'sr',
        'si'
    ]
    debits = [
        'sbc',
        'sbp',
        'sp',
        'sc'
    ]
    payment_types = [
        'sbp',
        'sbr',
        'sp',
        'sr'
    ]
    types = no_analysis_required + analysis_required


class SaleHeader(ModuleTransactionBase, TransactionHeader):
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=ModuleTransactionBase.types
    )
    matched_to = models.ManyToManyField(
        'self', through='SaleMatching', symmetrical=False)

    class Meta:
        permissions = [
            # enquiry perms
            ("view_transactions_enquiry", "Can view transactions"),
            # report perms
            ("view_age_debtors_report", "Can view aged debtors report"),
            # transactions
            ("create_brought_forward_invoice_transaction",
             "Can create brought forward invoice"),
            ("create_brought_forward_credit_note_transaction",
             "Can create brought forward credit note"),
            ("create_brought_forward_receipt_transaction",
             "Can create brought forward receipt"),
            ("create_brought_forward_refund_transaction",
             "Can create brought forward refund"),
            ("create_invoice_transaction", "Can create invoice"),
            ("create_credit_note_transaction", "Can create credit note"),
            ("create_receipt_transaction", "Can create receipt"),
            ("create_refund_transaction", "Can create refund"),
            ("edit_brought_forward_invoice_transaction",
             "Can edit brought forward invoice"),
            ("edit_brought_forward_credit_note_transaction",
             "Can edit brought forward credit note"),
            ("edit_brought_forward_receipt_transaction",
             "Can edit brought forward receipt"),
            ("edit_brought_forward_refund_transaction",
             "Can edit brought forward refund"),
            ("edit_invoice_transaction", "Can edit invoice"),
            ("edit_credit_note_transaction", "Can edit credit note"),
            ("edit_receipt_transaction", "Can edit receipt"),
            ("edit_refund_transaction", "Can edit refund"),
            ("view_brought_forward_invoice_transaction",
             "Can view brought forward invoice"),
            ("view_brought_forward_credit_note_transaction",
             "Can view brought forward credit note"),
            ("view_brought_forward_receipt_transaction",
             "Can view brought forward receipt"),
            ("view_brought_forward_refund_transaction",
             "Can view brought forward refund"),
            ("view_invoice_transaction", "Can view invoice"),
            ("view_credit_note_transaction", "Can view credit note"),
            ("view_receipt_transaction", "Can view receipt"),
            ("view_refund_transaction", "Can view refund"),
            ("void_brought_forward_invoice_transaction",
             "Can void brought forward invoice"),
            ("void_brought_forward_credit_note_transaction",
             "Can void brought forward credit note"),
            ("void_brought_forward_receipt_transaction",
             "Can void brought forward receipt"),
            ("void_brought_forward_refund_transaction",
             "Can void brought forward refund"),
            ("void_invoice_transaction", "Can void invoice"),
            ("void_credit_note_transaction", "Can void credit note"),
            ("void_receipt_transaction", "Can void receipt"),
            ("void_refund_transaction", "Can void refund"),
        ]

    def get_type_transaction(self):
        if self.type == "sbi":
            return BroughtForwardInvoice(header=self)
        if self.type == "sbc":
            return BroughtForwardCreditNote(header=self)
        if self.type == "sbp":
            return BroughtForwardReceipt(header=self)
        if self.type == "sbr":
            return BroughtForwardRefund(header=self)
        if self.type == "si":
            return Invoice(header=self)
        if self.type == "sc":
            return CreditNote(header=self)
        if self.type == "sp":
            return Receipt(header=self)
        if self.type == "sr":
            return Refund(header=self)

    def get_absolute_url(self):
        return reverse("sales:view", kwargs={"pk": self.pk})


class SaleLine(ModuleTransactionBase, TransactionLine):
    header = models.ForeignKey(SaleHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey(
        'nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)
    vat_code = models.ForeignKey(
        Vat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="sale_good_line")
    vat_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="sale_vat_line")
    total_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="sale_total_line")
    vat_transaction = models.ForeignKey(
        'vat.VatTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="sale_line_vat_transaction")
    type = models.CharField(
        max_length=3,
        choices=SaleHeader.types
        # see note on parent class for more info
    )

    # It does not make sense that a line would exist without a nominal transaction but the purchase line is created
    # before the nominal transaction so it must do the create without the id for the nominal transaction

    class Meta:
        ordering = ['line_no']

    @classmethod
    def fields_to_update(self):
        return [
            "description",
            "goods",
            "vat",
            "nominal",
            "vat_code",
            "type"
        ]


class SaleMatching(MatchedHeaders):
    # matched_by is the header record through which
    # all the other transactions were matched
    matched_by = models.ForeignKey(
        SaleHeader,
        on_delete=models.CASCADE,
        related_name="matched_by_these",
    )
    # matched_to is a header record belonging to
    # the set 'all the other transactions' described above
    matched_to = models.ForeignKey(
        SaleHeader,
        on_delete=models.CASCADE,
        related_name="matched_to_these"
    )
    matched_by_type = models.CharField(
        max_length=3,
        choices=SaleHeader.types
        # see note on parent class for more info
    )
    matched_to_type = models.CharField(
        max_length=3,
        choices=SaleHeader.types
        # see note on parent class for more info
    )

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

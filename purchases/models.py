from uuid import uuid4

from accountancy.models import (CashBookEntryMixin,
                                ControlAccountInvoiceTransactionMixin,
                                ControlAccountPaymentTransactionMixin,
                                MatchedHeaders, Transaction, TransactionHeader,
                                TransactionLine, VatTransactionMixin)
from contacts.models import Contact
from django.conf import settings
from django.db import models
from django.db.models import Q
from simple_history import register
from vat.models import Vat


class Supplier(Contact):
    """
    Do not create or update via the Supplier model because it does
    not audit records.  Always use the Contact model instead.
    """
    class Meta:
        proxy = True


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


class ModuleTransactionBase:
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
    payment_type = [
        'pbp',
        'pbr',
        'pp',
        'pr'
    ]
    type_choices = no_analysis_required + analysis_required


class PurchaseHeader(ModuleTransactionBase, TransactionHeader):
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=ModuleTransactionBase.type_choices
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


register(PurchaseHeader)


class PurchaseLine(ModuleTransactionBase, TransactionLine):
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
        choices=PurchaseHeader.type_choices
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


register(PurchaseLine)


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
        choices=PurchaseHeader.type_choices
        # see note on parent class for more info
    )
    matched_to_type = models.CharField(
        max_length=3,
        choices=PurchaseHeader.type_choices
        # see note on parent class for more info
    )
    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

    @classmethod
    def get_not_fully_matched_at_period(cls, headers, period):
        return super(PurchaseMatching, cls).get_not_fully_matched_at_period(headers, period)


register(PurchaseMatching)

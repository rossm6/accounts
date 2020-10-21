from uuid import uuid4

from django.conf import settings
from django.db import models
from simple_history import register

from accountancy.models import (Audit, CashBookEntryMixin, Contact,
                                ControlAccountInvoiceTransactionMixin,
                                ControlAccountPaymentTransactionMixin,
                                MatchedHeaders, Transaction, TransactionHeader,
                                TransactionLine, VatTransactionMixin)
from accountancy.signals import audit_post_delete
from utils.helpers import \
    disconnect_simple_history_receiver_for_post_delete_signal
from vat.models import Vat


class Customer(Audit, Contact):
    pass


register(Customer)
disconnect_simple_history_receiver_for_post_delete_signal(Customer)
audit_post_delete.connect(Customer.post_delete,
                          sender=Customer, dispatch_uid=uuid4())


class SalesTransaction(Transaction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = "SL"
        self._vat_type = "o" # output vat

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
    payment_type = [
        'sbp',
        'sbr',
        'sp',
        'sr'
    ]
    type_choices = no_analysis_required + analysis_required

class SaleHeader(ModuleTransactionBase, TransactionHeader):
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=ModuleTransactionBase.type_choices
    )
    matched_to = models.ManyToManyField(
        'self', through='SaleMatching', symmetrical=False)

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


register(SaleHeader)


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
        choices=SaleHeader.type_choices
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


register(SaleLine)


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
        choices=SaleHeader.type_choices
        # see note on parent class for more info
    )
    matched_to_type = models.CharField(
        max_length=3,
        choices=SaleHeader.type_choices
        # see note on parent class for more info
    )

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()


register(SaleMatching)

from django.conf import settings
from django.db import models
from simple_history import register

from accountancy.models import (CashBookEntryMixin, Contact,
                                ControlAccountInvoiceTransactionMixin,
                                ControlAccountPaymentTransactionMixin,
                                MatchedHeaders, Transaction, TransactionHeader,
                                TransactionLine)
from items.models import Item
from vat.models import Vat


class Customer(Contact):
    pass


register(Customer)


class SalesTransaction(Transaction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = "SL"


class BroughtForwardInvoice(SalesTransaction):
    pass


class Invoice(ControlAccountInvoiceTransactionMixin, SalesTransaction):
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


class SaleHeader(TransactionHeader):
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
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    type_choices = no_analysis_required + analysis_required
    cash_book = models.ForeignKey(
        'cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=type_choices
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


class SaleLineQuerySet(models.QuerySet):

    def line_bulk_update(self, instances):
        return self.bulk_update(
            instances,
            [
                "line_no",
                "description",
                "goods",
                "vat",
                "nominal",
                "vat_code"
            ]
        )


class SaleLine(TransactionLine):
    header = models.ForeignKey(SaleHeader, on_delete=models.CASCADE)
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, null=True, blank=True)
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

    # It does not make sense that a line would exist without a nominal transaction but the purchase line is created
    # before the nominal transaction so it must do the create without the id for the nominal transaction

    objects = SaleLineQuerySet.as_manager()

    class Meta:
        ordering = ['line_no']


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

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

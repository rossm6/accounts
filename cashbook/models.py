from django.db import models

from accountancy.models import TransactionHeader, TransactionLine, MultiLedgerTransactions, Transaction, CashBookPaymentTransactionMixin
from vat.models import Vat
from purchases.models import PurchaseHeader
from sales.models import SaleHeader

class CashBook(models.Model):
    name = models.CharField(max_length=10)
    nominal = models.ForeignKey('nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class CashBookTransaction(Transaction):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = "CB"

class Payment(CashBookPaymentTransactionMixin, CashBookTransaction):
    pass

class BroughtForwardPayment(CashBookTransaction):
    pass

class Refund(Payment):
    pass

class BroughtForwardRefund(CashBookTransaction):
    pass


class CashBookHeader(TransactionHeader):
    no_analysis_required = [
        ('cbp', 'Brought Forward Payment'),
        ('cbr', 'Brought Forward Receipt'),
    ]
    analysis_required = [
        ('cp', 'Payment'),
        ('cr', 'Receipt'),
    ]
    no_lines_required = []
    lines_required = [
        ('cbp', 'Brought Forward Payment'),
        ('cbr', 'Brought Forward Receipt'),
        ('cp', 'Payment'),
        ('cr', 'Receipt'),
    ]
    positives = [
        'cbr',
        'cr'
    ]
    negatives = [
        'cbp',
        'cp'
    ]
    credits = [
        'cbr',
        'cr'
    ]
    debits = [
        'cbp',
        'cp'
    ]
    payment_type = [
        'cbp',
        'cp',
        'cbr',
        'cr'
    ]
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    type_choices = no_analysis_required + analysis_required
    cash_book = models.ForeignKey(CashBook, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=type_choices
    )
    # payee to add

    def get_type_transaction(self):
        if self.type == "cbp":
            return BroughtForwardPayment(header=self)
        if self.type == "cbr":
            return BroughtForwardRefund(header=self)
        if self.type == "cp":
            return Payment(header=self)
        if self.type == "cr":
            return Refund(header=self)


class CashBookLineQuerySet(models.QuerySet):

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


class CashBookLine(TransactionLine):
    header = models.ForeignKey(CashBookHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey('nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="cash_book_good_line")
    vat_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="cash_book_vat_line")
    total_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="cash_book_total_line")

    objects = CashBookLineQuerySet.as_manager()

    class Meta:
        ordering = ['line_no']


all_module_types = (
    PurchaseHeader.analysis_required +
    SaleHeader.analysis_required +
    CashBookHeader.analysis_required
)

class CashBookTransaction(MultiLedgerTransactions):
    cash_book = models.ForeignKey(CashBook, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=all_module_types)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'header', 'line', 'field'], name="cashbook_unique_batch")
        ]
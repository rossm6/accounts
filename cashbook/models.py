from django.db import models
from simple_history import register

from accountancy.models import (CashBookPaymentTransactionMixin,
                                MultiLedgerTransactions, Transaction,
                                TransactionHeader, TransactionLine,
                                UIDecimalField, VatTransactionMixin)
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from vat.models import Vat


class CashBook(models.Model):
    name = models.CharField(max_length=10)
    nominal = models.ForeignKey(
        'nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


register(CashBook)


class CashBookTransaction(Transaction):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = "CB"

class Payment(VatTransactionMixin, CashBookPaymentTransactionMixin, CashBookTransaction):
    pass


class BroughtForwardPayment(CashBookTransaction):
    pass


class Refund(Payment):
    pass


class BroughtForwardRefund(CashBookTransaction):
    pass


class ModuleTransactionBase:
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
    type_choices = no_analysis_required + analysis_required


class CashBookHeader(ModuleTransactionBase, TransactionHeader):
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    vat_types = [
        ("i", "Input"),
        ("o", "Output")
    ]
    cash_book = models.ForeignKey(CashBook, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=ModuleTransactionBase.type_choices
    )
    vat_type = models.CharField(
        max_length=2,
        choices=vat_types,
        null=True,
        blank=True
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


register(CashBookHeader)


# class CashBookLineQuerySet(models.QuerySet):

#     def line_bulk_update(self, instances):
#         return self.bulk_update(
#             instances,
#             [
#                 "line_no",
#                 "description",
#                 "goods",
#                 "vat",
#                 "nominal",
#                 "vat_code"
#             ]
#         )


class CashBookLine(ModuleTransactionBase, TransactionLine):
    header = models.ForeignKey(CashBookHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey(
        'nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)
    vat_code = models.ForeignKey(
        Vat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_book_good_line")
    vat_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_book_vat_line")
    total_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_book_total_line")
    vat_transaction = models.ForeignKey(
        'vat.VatTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_book_line_vat_transaction")
    type = models.CharField(
        max_length=3,
        choices=CashBookHeader.type_choices
        # see note on parent class for more info
    )

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


register(CashBookLine)

all_module_types = (
    PurchaseHeader.analysis_required +
    SaleHeader.analysis_required +
    CashBookHeader.analysis_required
)


class CashBookTransaction(MultiLedgerTransactions):
    cash_book = models.ForeignKey(CashBook, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=all_module_types)
    value = UIDecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'header', 'line', 'field'], name="cashbook_unique_batch")
        ]

    @classmethod
    def fields_to_update(cls):
        return [
            "value",
            "ref",
            "period",
            "date",
            "type"
        ]


register(CashBookTransaction)

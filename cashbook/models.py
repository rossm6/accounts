from accountancy.mixins import (CashBookPaymentTransactionMixin,
                                VatTransactionMixin, AuditMixin)
from accountancy.models import (MultiLedgerTransactions, Transaction,
                                TransactionHeader, TransactionLine)
from django.db import models
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from simple_history import register
from vat.models import Vat


class CashBook(AuditMixin, models.Model):
    name = models.CharField(max_length=10)
    nominal = models.ForeignKey(
        'nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class CashBookTransaction(Transaction):
    module = "CB"


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
    payment_types = [
        'cbp',
        'cp',
        'cbr',
        'cr'
    ]
    types = no_analysis_required + analysis_required


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
        choices=ModuleTransactionBase.types
    )
    vat_type = models.CharField(
        max_length=2,
        choices=vat_types,
        null=True,
        blank=True
    )
    # payee to add

    class Meta:
        permissions = [
            # enquiry perms
            ("view_transactions_enquiry", "Can view transactions"),
            # transaction perms
            ("create_brought_forward_payment_transaction", "Can create brought forward payment"),
            ("create_brought_forward_receipt_transaction", "Can create brought forward receipt"),
            ("create_payment_transaction", "Can create payment"),
            ("create_receipt_transaction", "Can create receipt"),
            ("edit_brought_forward_payment_transaction", "Can edit brought forward payment"),
            ("edit_brought_forward_receipt_transaction", "Can edit brought forward receipt"),
            ("edit_payment_transaction", "Can edit payment"),
            ("edit_receipt_transaction", "Can edit receipt"),
            ("view_brought_forward_payment_transaction", "Can view brought forward payment"),
            ("view_brought_forward_receipt_transaction", "Can view brought forward receipt"),
            ("view_payment_transaction", "Can view payment"),
            ("view_receipt_transaction", "Can view receipt"),
            ("void_brought_forward_payment_transaction", "Can void brought forward payment"),
            ("void_brought_forward_receipt_transaction", "Can void brought forward receipt"),
            ("void_payment_transaction", "Can void payment"),
            ("void_receipt_transaction", "Can void receipt"),
        ]


    def get_type_transaction(self):
        if self.type == "cbp":
            return BroughtForwardPayment(header=self)
        if self.type == "cbr":
            return BroughtForwardRefund(header=self)
        if self.type == "cp":
            return Payment(header=self)
        if self.type == "cr":
            return Refund(header=self)


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
        choices=CashBookHeader.types
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


all_module_types = (
    PurchaseHeader.analysis_required +
    SaleHeader.analysis_required +
    CashBookHeader.analysis_required
)

class CashBookTransaction(MultiLedgerTransactions):
    cash_book = models.ForeignKey(CashBook, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=all_module_types)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        default=0
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

    def update_details_from_header(self, header):
        super().update_details_from_header(header)
        self.cash_book = header.cash_book
        self.type = header.type
        self.value = header.total
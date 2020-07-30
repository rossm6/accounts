from django.db import models

from accountancy.models import TransactionHeader, TransactionLine
from nominals.models import Nominal
from vat.models import Vat


class CashBook(models.Model):
    name = models.CharField(max_length=10)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE, null=True, blank=True)

class CashBookHeader(TransactionHeader):
    no_analysis_required = [
        ('cbp', 'Brought Forward Payment'),
        ('cbr', 'Brought Forward Receipt'),
        ('cp', 'Payment'),
        ('cr', 'Receipt'),
    ]
    analysis_required = [
        ('cp', 'Payment'),
        ('cr', 'Receipt'),
    ]
    no_lines_required = [
        ('cbp', 'Brought Forward Payment'),
        ('cbr', 'Brought Forward Receipt'),
    ]
    lines_required = [
        ('cp', 'Payment'),
        ('cr', 'Receipt'),
    ]
    credits = [
        'cbr',
        'cr'
    ]
    debits = [
        'cbr',
        'cr'
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

    objects = CashBookLineQuerySet.as_manager()

    class Meta:
        ordering = ['line_no']

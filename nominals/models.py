from django.db import models
from mptt.models import MPTTModel, TreeForeignKey

from accountancy.models import TransactionHeader, TransactionLine, DecimalBaseModel
from purchases.models import PurchaseHeader
from vat.models import Vat


class Nominal(MPTTModel):
    name = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name

class NominalHeader(TransactionHeader):
    analysis_required = [
        ('nj', 'Journal')
    ]
    type = models.CharField(
        max_length=2,
        choices=analysis_required
    )


class NominalLine(TransactionLine):
    header = models.ForeignKey(NominalHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")
    nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, on_delete=models.CASCADE)

all_module_types = PurchaseHeader.type_choices + NominalHeader.analysis_required

class NominalTransaction(DecimalBaseModel):
    module = models.CharField(max_length=3) # e.g. 'PL' for purchase ledger
    # we don't bother with ForeignKeys to the header and line models
    # because this would require generic foreign keys which means extra overhead
    # in the SQL queries
    # and we only need the header and line number anyway to group within
    # the nominal transactions table
    header = models.PositiveIntegerField()
    line = models.PositiveIntegerField()
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    ref = models.CharField(max_length=100) # CHECK LENGTH
    period = models.CharField(max_length=6)
    date = models.DateField()
    created = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=10, choices=all_module_types)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['module', 'header', 'line'], name="unique_batch")
        ]
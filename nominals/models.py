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
    lines_required = [
        ('nj', 'Journal')
    ]
    type = models.CharField(
        max_length=2,
        choices=analysis_required
    )

class NominalLineQuerySet(models.QuerySet):

    def line_bulk_update(self, instances):
        return self.bulk_update(
            instances,
            [
                "line_no",
                'description',
                'goods',
                'vat',
                "nominal",
                "vat_code",
            ]
        )

class NominalLine(TransactionLine):
    header = models.ForeignKey(NominalHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, on_delete=models.CASCADE, related_name="nominal_good_line")
    vat_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, on_delete=models.CASCADE, related_name="nominal_vat_line")

    objects = NominalLineQuerySet.as_manager()

all_module_types = PurchaseHeader.type_choices + NominalHeader.analysis_required


class NominalTransactionQuerySet(models.QuerySet):

    def line_bulk_update(self, instances):
        return self.bulk_update(
            instances,
            [
                "nominal",
                "value",
                "ref",
                "period",
                "date",
                "type"
            ]
        )

class NominalTransaction(DecimalBaseModel):
    module = models.CharField(max_length=3) # e.g. 'PL' for purchase ledger
    # we don't bother with ForeignKeys to the header and line models
    # because this would require generic foreign keys which means extra overhead
    # in the SQL queries
    # and we only need the header and line number anyway to group within
    # the nominal transactions table
    header = models.PositiveIntegerField()
    line = models.PositiveIntegerField() # if a line transaction is created e.g. Purchase or Nominal Line, this will just be the primary key of the line record
    # but sometimes there won't be any lines e.g. a payment.  So the line will have to be set manually
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
    # User should never see this
    field_choices = [
        ('g', 'Goods'),
        ('v', 'Vat'),
        ('t', 'Total')
    ]
    field = models.CharField(max_length=2, choices=field_choices)
    # We had uniqueness set on the fields "module", "header" and "line"
    # but of course an analysis line can map to many different nominal transactions
    # at a minimum there is the goods and the vat on the analysis line
    # field is therefore a way of distinguishing the transactions and
    # guranteeing uniqueness
    type = models.CharField(max_length=10, choices=all_module_types)

    objects = NominalTransactionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['module', 'header', 'line', 'field'], name="unique_batch")
        ]
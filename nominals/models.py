from django.db import models
from mptt.models import MPTTModel, TreeForeignKey

from accountancy.models import TransactionHeader, TransactionLine, DecimalBaseModel
from purchases.models import PurchaseHeader
from vat.models import Vat

from django.conf import settings

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
    credits = []
    debits = []
    type = models.CharField(
        max_length=2,
        choices=analysis_required
    )


    def create_nominal_transactions_for_line(self, nom_tran_cls, module, line, vat_nominal):
        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=line.goods,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="g"
                )
            )
        if line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=module,
                    header=self.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=self.ref,
                    period=self.period,
                    date=self.date,
                    type=self.type,
                    field="v"
                )
            )
        return trans


    def create_nominal_transactions(self, nom_cls, nom_tran_cls, line_cls, module, vat_control_name, lines):
        try:
            vat_nominal = nom_cls.objects.get(name=vat_control_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            vat_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)
        nominal_transactions = []
        for line in lines:
            nominal_transactions += self.create_nominal_transaction_for_line(
                nom_tran_cls, module, line, vat_nominal
            )
        if nominal_transactions:
            nominal_transactions = self.nom_tran_cls.objects.bulk_create(nominal_transactions)
            # THIS IS CRAZILY INEFFICIENT !!!!
            for line in lines:
                line_nominal_trans = {
                    nominal_transaction.field: nominal_transaction
                    for nominal_transaction in nominal_transactions
                    if nominal_transaction.line == line.pk
                }
                line.add_nominal_transactions(line_nominal_trans)
            line_cls.objects.bulk_update(lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])


    def edit_nominal_transactions():
        pass
        


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
    goods_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_good_line")
    vat_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_vat_line")

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
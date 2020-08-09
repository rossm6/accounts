from django.db import models
from mptt.models import MPTTModel, TreeForeignKey

from accountancy.models import TransactionHeader, TransactionLine, DecimalBaseModel
from purchases.models import PurchaseHeader
from vat.models import Vat

from django.conf import settings


class Nominal(MPTTModel):
    name = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE,
                            null=True, blank=True, related_name='children')

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

    def _create_nominal_transactions_for_line(self, nom_tran_cls, module, line, vat_nominal):
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

    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal):
        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = line.goods
            tran.ref = self.ref
            tran.period = self.period
            tran.date = self.date
            tran.type = self.type
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = line.vat
            tran.ref = self.ref
            tran.period = self.period
            tran.date = self.date
            tran.type = self.type

        _nom_trans_to_update = []
        _nom_trans_to_delete = []

        if 'g' in nom_trans:
            if nom_trans["g"].value:
                _nom_trans_to_update.append(nom_trans["g"])
            else:
                _nom_trans_to_delete.append(nom_trans["g"])
                line.goods_nominal_transaction = None
        if 'v' in nom_trans:
            if nom_trans["v"].value:
                _nom_trans_to_update.append(nom_trans["v"])
            else:
                _nom_trans_to_delete.append(nom_trans["v"])
                line.vat_nominal_transaction = None

        return _nom_trans_to_update, _nom_trans_to_delete

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        if (vat_nominal := kwargs.get("vat_nominal")) is None:
            try:
                vat_nominal_name = kwargs.get("vat_nominal_name")
                vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                vat_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        nominal_transactions = []
        lines = kwargs.get("lines", [])
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                nom_tran_cls, module, line, vat_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.bulk_create(
                nominal_transactions)
            # THIS IS CRAZILY INEFFICIENT !!!!
            for line in lines:
                line_nominal_trans = {
                    nominal_transaction.field: nominal_transaction
                    for nominal_transaction in nominal_transactions
                    if nominal_transaction.line == line.pk
                }
                line.add_nominal_transactions(line_nominal_trans)
            line_cls = kwargs.get('line_cls')
            line_cls.objects.bulk_update(
                lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, module, **kwargs):
        nom_trans_to_update = []
        nom_trans_to_delete = []

        try:
            vat_nominal_name = kwargs.get("vat_nominal_name")
            vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
        except nom_cls.DoesNotExist:
            # bult into system so cannot not exist
            vat_nominal = nom_cls.objects.get(
                name=settings.DEFAULT_SYSTEM_SUSPENSE)

        existing_nom_trans = kwargs.get('existing_nom_trans')

        new_lines = kwargs.get("new_lines")
        updated_lines = kwargs.get("updated_lines")
        deleted_lines = kwargs.get("deleted_lines")

        if updated_lines:
            for line in updated_lines:
                nominal_trans = {
                    tran.field: tran
                    for tran in existing_nom_trans
                    if tran.line == line.pk
                }
                to_update, to_delete = self._edit_nominal_transactions_for_line(
                    nominal_trans, line, vat_nominal)
                nom_trans_to_update += to_update
                nom_trans_to_delete += to_delete

        if deleted_lines:
            for line in deleted_lines:
                nominal_trans = [
                    tran
                    for tran in existing_nom_trans
                    if tran.line == line.pk
                ]
                nom_trans_to_delete += nominal_trans

        line_cls = kwargs.get('line_cls')
        self.create_nominal_transactions(
            nom_cls, nom_tran_cls, module,
            lines=new_lines,
            line_cls=line_cls,
            vat_nominal=vat_nominal
        )
        nom_tran_cls.objects.line_bulk_update(nom_trans_to_update)
        nom_tran_cls.objects.filter(
            pk__in=[nom_tran.pk for nom_tran in nom_trans_to_delete]).delete()


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
    vat_code = models.ForeignKey(
        Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_good_line")
    vat_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_vat_line")

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
    module = models.CharField(max_length=3)  # e.g. 'PL' for purchase ledger
    # we don't bother with ForeignKeys to the header and line models
    # because this would require generic foreign keys which means extra overhead
    # in the SQL queries
    # and we only need the header and line number anyway to group within
    # the nominal transactions table
    header = models.PositiveIntegerField()
    # if a line transaction is created e.g. Purchase or Nominal Line, this will just be the primary key of the line record
    line = models.PositiveIntegerField()
    # but sometimes there won't be any lines e.g. a payment.  So the line will have to be set manually
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    ref = models.CharField(max_length=100)  # CHECK LENGTH
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
            models.UniqueConstraint(
                fields=['module', 'header', 'line', 'field'], name="unique_batch")
        ]

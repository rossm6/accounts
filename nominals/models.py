from itertools import groupby

from django.conf import settings
from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from simple_history import register

from accountancy.models import (MultiLedgerTransactions, Transaction,
                                TransactionHeader, TransactionLine,
                                UIDecimalField, VatTransactionMixin)
from cashbook.models import CashBookHeader
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from utils.helpers import bulk_delete_with_history
from vat.models import Vat


class Nominal(MPTTModel):
    name = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE,
                            null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name


register(Nominal)


class NominalTransaction(Transaction):
    def __init__(self, *args, **kwargs):
        self.header_obj = kwargs.get("header")
        self.module = "NL"

    def create_nominal_transactions(self, *args, **kwargs):
        return

    def edit_nominal_transactions(self, *args, **kwargs):
        return


"""
We are repeating ourselves here.  Need to use inheritance.
"""


class Journal(VatTransactionMixin, NominalTransaction):
    def _create_nominal_transactions_for_line(self, nom_tran_cls, line, vat_nominal):
        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=line.goods,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="g"
                )
            )
        if line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="v"
                )
            )
        return trans

    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal):

        for tran_field, tran in nom_trans.items():
            tran.ref = self.header_obj.ref
            tran.period = self.header_obj.period
            tran.date = self.header_obj.date
            tran.type = self.header_obj.type

        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = line.goods
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = line.vat

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

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        if (vat_nominal := kwargs.get("vat_nominal")) is None:
            try:
                vat_nominal_name = kwargs.get("vat_nominal_name")
                vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                vat_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        nominal_transactions = []
        if lines := kwargs.get("lines", []):
            lines = sorted(lines, key=lambda l: l.pk)
        for line in lines:
            nominal_transactions += self._create_nominal_transactions_for_line(
                nom_tran_cls, line, vat_nominal
            )
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.audited_bulk_create(
                nominal_transactions)
            nominal_transactions = sorted(
                nominal_transactions, key=lambda n: n.line)
            for line, (key, line_nominal_trans) in zip(lines, groupby(nominal_transactions, lambda n: n.line)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
                line.add_nominal_transactions(nom_tran_map)
            line_cls = kwargs.get('line_cls')
            line_cls.objects.audited_bulk_update(
                lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])

            return nominal_transactions

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
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
        existing_nom_trans = sorted(existing_nom_trans, key=lambda n: n.line)

        if new_lines := kwargs.get("new_lines"):
            sorted(new_lines, key=lambda l: l.pk)
        if updated_lines := kwargs.get("updated_lines"):
            sorted(updated_lines, key=lambda l: l.pk)
        if deleted_lines := kwargs.get("deleted_lines"):
            sorted(deleted_lines, key=lambda l: l.pk)

        if updated_lines:
            lines_to_update = [line.pk for line in updated_lines]
            nom_trans_to_update = [
                tran for tran in existing_nom_trans if tran.line in lines_to_update]
            nom_trans_to_update = sorted(
                nom_trans_to_update, key=lambda n: n.line)
            for line, (key, line_nominal_trans) in zip(updated_lines, groupby(nom_trans_to_update, key=lambda n: n.line)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
                to_update, to_delete = self._edit_nominal_transactions_for_line(
                    nom_tran_map, line, vat_nominal)
                nom_trans_to_delete += to_delete

        nom_trans_to_update = [
            tran for tran in nom_trans_to_update if tran not in nom_trans_to_delete]

        if deleted_lines:
            lines_to_delete = [line.pk for line in deleted_lines]
            nom_trans_to_delete = [
                tran for tran in existing_nom_trans if tran.line in lines_to_delete]
            nom_trans_to_delete = sorted(
                nom_trans_to_delete, key=lambda n: n.line)
            for line, (key, nom_trans) in zip(deleted_lines, groupby(nom_trans_to_delete, key=lambda n: n.line)):
                nom_trans_to_delete += list(nom_trans)

        line_cls = kwargs.get('line_cls')
        new_nom_trans = self.create_nominal_transactions(
            nom_cls, nom_tran_cls,
            lines=new_lines,
            line_cls=line_cls,
            vat_nominal=vat_nominal
        )
        nom_trans = (new_nom_trans if new_nom_trans else []) + \
            nom_trans_to_update
        nom_tran_cls.objects.audited_bulk_line_update(nom_trans_to_update)
        bulk_delete_with_history(
            nom_trans_to_delete,
            nom_tran_cls
        )
        return nom_trans


class ModuleTransactionBase:
    analysis_required = [
        ('nj', 'Journal')
    ]
    lines_required = [
        ('nj', 'Journal')
    ]
    positives = ['nj']
    negatives = []
    credits = []
    debits = ['nj']


class NominalHeader(ModuleTransactionBase, TransactionHeader):
    vat_types = [
        ("i", "Input"),
        ("o", "Output")
    ]
    type = models.CharField(
        max_length=2,
        choices=ModuleTransactionBase.analysis_required
    )
    vat_type = models.CharField(
        max_length=2,
        choices=vat_types,
        null=True,
        blank=True
    )

    def get_type_transaction(self):
        if self.type == "nj":
            return Journal(header=self)


register(NominalHeader)


# class NominalLineQuerySet(models.QuerySet):

#     def line_bulk_update(self, instances):
#         return self.bulk_update(
#             instances,
#             [
#                 "line_no",
#                 'description',
#                 'goods',
#                 'vat',
#                 "nominal",
#                 "vat_code",
#             ]
#         )


class NominalLine(ModuleTransactionBase, TransactionLine):
    header = models.ForeignKey(NominalHeader, on_delete=models.CASCADE)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    vat_code = models.ForeignKey(
        Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_good_line")
    vat_nominal_transaction = models.ForeignKey(
        'nominals.NominalTransaction', null=True, on_delete=models.SET_NULL, related_name="nominal_vat_line")
    vat_transaction = models.ForeignKey(
        'vat.VatTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name="nominal_line_vat_transaction")
    type = models.CharField(
        max_length=3,
        choices=NominalHeader.analysis_required
        # see note on parent class for more info
    )

    @classmethod
    def fields_to_update(cls):
        return [
            "line_no",
            'description',
            'goods',
            'vat',
            "nominal",
            "vat_code",
            "type"
        ]


register(NominalLine)


# class NominalTransactionQuerySet(models.QuerySet):

#     # DO WE NEED THIS?
#     # I THINK IT SLIPPED IN BY ACCIDENT
#     def line_bulk_update(self, instances):
#         return self.bulk_update(
#             instances,
#             [
#                 "nominal",
#                 "value",
#                 "ref",
#                 "period",
#                 "date",
#                 "type"
#             ]
#         )


class NominalTransaction(MultiLedgerTransactions):
    all_module_types = (
        PurchaseHeader.analysis_required +
        NominalHeader.analysis_required +
        SaleHeader.analysis_required +
        CashBookHeader.analysis_required
    )
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
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
                fields=['module', 'header', 'line', 'field'], name="nominal_unique_batch")
        ]

    @classmethod
    def fields_to_update(cls):
        return [
            "nominal",
            "value",
            "ref",
            "period",
            "date",
            "type"
        ]


register(NominalTransaction)

from itertools import groupby

from accountancy.helpers import bulk_delete_with_history
from accountancy.mixins import (AuditMixin, BaseNominalTransactionMixin,
                                BaseNominalTransactionPerLineMixin,
                                VatTransactionMixin)
from accountancy.models import (MultiLedgerTransactions, Transaction,
                                TransactionHeader, TransactionLine,
                                UIDecimalField)
from cashbook.models import CashBookHeader
from django.conf import settings
from django.db import models
from django.shortcuts import reverse
from mptt.models import MPTTModel, TreeForeignKey
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from simple_history import register
from vat.models import Vat


class Nominal(AuditMixin, MPTTModel):
    name = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE,
                            null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("nominals:nominal_detail", kwargs={"pk": self.pk})

class NominalTransaction(Transaction):
    module = "NL"


class Journal(
        VatTransactionMixin,
        BaseNominalTransactionPerLineMixin,
        BaseNominalTransactionMixin,
        NominalTransaction):
    pass


class ModuleTransactions:
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
    payment_types = []
    types = analysis_required


class NominalHeader(ModuleTransactions, TransactionHeader):
    vat_types = [
        ("i", "Input"),
        ("o", "Output")
    ]
    type = models.CharField(
        max_length=2,
        choices=ModuleTransactions.types
    )
    vat_type = models.CharField(
        max_length=2,
        choices=vat_types,
        null=True,
        blank=True
    )

    class Meta:
        permissions = [
            # enquiry perms
            ("view_transactions_enquiry", "Can view transactions"),
            # report perms
            ("view_trial_balance_report", "Can view trial balance report"),
            # transactions
            ("create_journal_transaction", "Can create journal"),
            ("edit_journal_transaction", "Can edit journal"),
            ("view_journal_transaction", "Can view journal"),
            ("void_journal_transaction", "Can void journal"),
        ]

    def get_type_transaction(self):
        if self.type == "nj":
            return Journal(header=self)

    def get_absolute_url(self):
        return reverse("nominals:view", kwargs={"pk": self.pk})

class NominalLine(ModuleTransactions, TransactionLine):
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
        choices=NominalHeader.types
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


class NominalTransaction(MultiLedgerTransactions):
    all_module_types = (
        PurchaseHeader.analysis_required +
        NominalHeader.analysis_required +
        SaleHeader.analysis_required +
        CashBookHeader.analysis_required
    )
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=all_module_types)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        default=0
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

    def update_details_from_header(self, header):
        super().update_details_from_header(header)
        self.type = header.type

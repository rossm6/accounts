import calendar
from datetime import date
from itertools import groupby

from accountancy.helpers import bulk_delete_with_history
from accountancy.mixins import (AuditMixin, BaseNominalTransactionMixin,
                                BaseNominalTransactionPerLineMixin,
                                VatTransactionMixin)
from accountancy.models import (MultiLedgerTransactions, NonAuditQuerySet,
                                Transaction, TransactionHeader,
                                TransactionLine, UIDecimalField)
from cashbook.models import CashBookHeader
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.shortcuts import reverse
from mptt.models import MPTTModel, TreeForeignKey
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from simple_history import register
from vat.models import Vat


def last_day_of_month(period):
    last_month_of_fy = period.month_start - relativedelta(months=+1)
    month, day = calendar.monthrange(
        last_month_of_fy.year, last_month_of_fy.month)
    return date(last_month_of_fy.year, last_month_of_fy.month, day)


class Nominal(AuditMixin, MPTTModel):
    NOMINAL_TYPES = [
        ("pl", "profit and loss"),
        ("b", "balance sheet")
    ]
    name = models.CharField(max_length=50)
    parent = TreeForeignKey('self', on_delete=models.CASCADE,
                            null=True, blank=True, related_name='children')
    type = models.CharField(
        max_length=2, choices=NOMINAL_TYPES, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'parent'], name="nominal_unique")
        ]

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
    types = analysis_required + [("nbf", "Nominal Brought Forward")]


class NominalHeader(ModuleTransactions, TransactionHeader):
    vat_types = [
        ("i", "Input"),
        ("o", "Output")
    ]
    type = models.CharField(
        max_length=3,
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


class NominalTransactionQuerySet(NonAuditQuerySet):

    def rollback_fy(self, financial_year):
        """
        Delete the brought forwards for `financial_year` which is an integer for the year e.g. 2020
        Ensure you pass therefore fy.financial_year, where fy is an instance of model FinancialYear,
        and not fy.

        E.g. 
        financial_year = 2020
        So will delete bfs posted into 01 2020
        Allowing the user to post back into FY 2019
        Afterwards carrying forward again i.e. doing a year end which
        will again post the bfs into 01 2020
        """
        self.filter(module="NL").filter(type="nbf").filter(
            period__fy__financial_year__gte=financial_year).delete()
        NominalHeader.objects.filter(type="nbf").filter(
            period__fy__financial_year__gte=financial_year).delete()

    def carry_forward(self, fy, period):
        """
        Calculate the carry forwards from FY so we can post them
        as brought forwards into `period`
        """
        # REMEMBER TO LOCK POSTS IN CALLING CODE I.E. THE VIEW
        retained_earnings, system_suspense = Nominal.objects.filter(
            name__in=["Retained Earnings", "System Suspense Account"]).order_by("name")
        pl = self.filter(period__fy=fy).filter(
            nominal__type="pl").aggregate(profit=Sum("value"))
        balance_sheet = self.filter(period__fy=fy).filter(
            nominal__type="b").values("nominal").annotate(total=Sum("value"))
        """
        We only really care about posting nominal transactions but nominaltransaction.header is
        unique per MODULE.  Since we want module=NL we create a blank header to satisfy this requirement.
        """
        header = NominalHeader.objects.create(
            date=last_day_of_month(period),
            ref=f"YEAR END {str(fy)}",
            period=period,
            total=0,
            status="c",
            type="nbf",
            vat_type=None,
        )
        header = header.pk
        line = 1
        bfs = []
        prev_retained_earnings_bf = False
        retained_earnings_bf = None
        if pl["profit"]:
            # i.e. a non zero profit
            # which means a profit or loss
            retained_earnings_bf = NominalTransaction.brought_forward(
                header, line, fy, period, pl["profit"], retained_earnings.pk
            )
            line += 1
        if balance_sheet:
            for nominal_pk_and_total in balance_sheet:
                if nominal_pk_and_total["nominal"] == retained_earnings.pk:
                    prev_retained_earnings_bf = True
                    if retained_earnings_bf:
                        retained_earnings_bf.value += nominal_pk_and_total["total"]
                        bf = retained_earnings_bf
                    else:
                        bf = retained_earnings_bf = NominalTransaction.brought_forward(
                            header, line, fy, period, nominal_pk_and_total["total"], nominal_pk_and_total["nominal"])
                else:
                    bf = NominalTransaction.brought_forward(
                        header, line, fy, period, nominal_pk_and_total["total"], nominal_pk_and_total["nominal"])
                bfs.append(bf)
                line += 1
            if not prev_retained_earnings_bf:
                if retained_earnings_bf:
                    bfs.append(retained_earnings_bf)
        else:
            if retained_earnings_bf:
                # i do not think this is possible but include in case i'm not seeing something
                # a profit or loss for the year means transactions which updated the balance sheet
                # otherwise they'd all cancel to zero
                # and if anything has ever updated the nominal it will always be c/f
                # so even if nothing is ever again posted in the balance sheet nominal there is always at least the c/f
                # thus i do not think this line of code can ever be hit
                # log this !
                bfs.append(retained_earnings_bf)
            else:
                # i.e. no transactions at all !
                # this is unlikely but was spotted during testing
                # a FY is considered finalised unless there is a year end posting
                # so we just post a zero value transaction to the suspense account
                # it will be invisible to the users
                bf = NominalTransaction.brought_forward(
                    header, line, fy, period, 0, system_suspense.pk
                )
                bfs.append(bf)
        self.bulk_create(bfs)


class NominalTransaction(MultiLedgerTransactions):
    all_module_types = (
        PurchaseHeader.analysis_required +
        NominalHeader.types +
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

    objects = NominalTransactionQuerySet.as_manager()

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

    @classmethod
    def brought_forward(cls, header, line, fy, period, value, nominal_pk):
        return cls(
            module="NL",
            header=header,
            line=line,
            date=last_day_of_month(period),
            ref=f"YEAR END {str(fy)}",
            period=period,
            type="nbf",
            field="t",
            value=value,
            nominal_id=nominal_pk
        )


def update_details_from_header(self, header):
    super().update_details_from_header(header)
    self.type = header.type

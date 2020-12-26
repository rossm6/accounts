from datetime import date

from controls.models import FinancialYear, Period
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction
from decimal import Decimal

PURCHASES_CONTROL_ACCOUNT = "Purchase Ledger Control"
SALES_CONTROL_ACCOUNT = "Sales Ledger Control"

class TrialBalanceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("nominals:trial_balance")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        
        # nominals

        # Profit and Loss
        revenues = Nominal.objects.create(name="Revenues")
        revenue = Nominal.objects.create(name="Revenue", parent=revenues)
        cls.sales = sales = Nominal.objects.create(name="Sales", parent=revenue)

        expenses = Nominal.objects.create(name="Expenses")
        expense = Nominal.objects.create(name="Expense", parent=expenses)
        cls.sundry = sundry = Nominal.objects.create(name="Sundry", parent=expense)

        # Balance Sheet
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.sales_ledger_control = sales_ledger_control = Nominal.objects.create(parent=current_assets, name=SALES_CONTROL_ACCOUNT)

        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_ledger_control = purchase_ledger_control = Nominal.objects.create(parent=current_liabilities, name=PURCHASES_CONTROL_ACCOUNT)
        cls.vat_control_account = vat_control_account = Nominal.objects.create(parent=current_liabilities, name=settings.DEFAULT_VAT_NOMINAL)

        today = date.today()

        # 2019
        cls.fy_2019 = fy_2019 = FinancialYear.objects.create(financial_year=2019)
        cls.p_201912 = p_201912 = Period.objects.create(
            fy=fy_2019, 
            period="01", 
            fy_and_period="201912", 
            month_end=date(2019, 12, 31)
        )

        # 2020
        cls.fy_2020 = fy_2020 = FinancialYear.objects.create(financial_year=2020)
        cls.p_202001 = p_202001 = Period.objects.create(
            fy=fy_2020, 
            period="01", 
            fy_and_period="202001", 
            month_end=date(2020, 1, 31)
        )
        cls.p_202002 = p_202002 = Period.objects.create(
            fy=fy_2020, 
            period="02", 
            fy_and_period="202002", 
            month_end=date(2020, 2, 29)     
        )

        # create a SL set of NL trans
        NominalTransaction.objects.create(
            header=1,
            line=1,
            module="SL",
            ref="1",
            period=p_202001,
            type="si",
            field="g",
            nominal=sales,
            value=-100,
            date=today
        )
        NominalTransaction.objects.create(
            header=1,
            line=2,
            module="SL",
            ref="1",
            period=p_202001,
            type="si",
            field="v",
            nominal=vat_control_account,
            value=-20,
            date=today
        )
        NominalTransaction.objects.create(
            header=1,
            line=3,
            module="SL",
            ref="1",
            period=p_202001,
            type="si",
            field="t",
            nominal=sales_ledger_control,
            value=120,
            date=today
        )
        # create a PL set of NL trans
        NominalTransaction.objects.create(
            header=1,
            line=1,
            module="PL",
            ref="1",
            period=p_202001,
            type="pi",
            field="g",
            nominal=sundry,
            value=100,
            date=today
        )
        NominalTransaction.objects.create(
            header=1,
            line=2,
            module="PL",
            ref="1",
            period=p_202001,
            type="pi",
            field="v",
            nominal=vat_control_account,
            value=20,
            date=today
        )
        NominalTransaction.objects.create(
            header=1,
            line=3,
            module="PL",
            ref="1",
            period=p_202001,
            type="pi",
            field="t",
            nominal=purchase_ledger_control,
            value=-120,
            date=today
        )

    def test(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            200
        )
        context_data = response.context_data
        debit_total = context_data["debit_total"]
        credit_total = context_data["credit_total"]
        """
        The totals are the total of the visible sums.  In this case the total of the visible debit balances
        is 220.

        However really the total of debits is 240.

        The user should have two nominals for vat really - vat input and vat output.  This would be a software change.
        """
        self.assertEqual(
            debit_total,
            220
        )
        self.assertEqual(
            credit_total,
            -220
        )
        ytd_debit_total = context_data["ytd_debit_total"]
        ytd_credit_total = context_data["ytd_credit_total"]
        self.assertEqual(
            ytd_debit_total,
            220
        )
        self.assertEqual(
            ytd_credit_total,
            -220
        )
        report = context_data["report"]
        nominals_map = {}
        for nominal_report in report:
            nominals_map[nominal_report["nominal"]] = nominal_report
        sales = nominals_map["Sales"]
        sundry = nominals_map["Sundry"]
        sales_ledger_control = nominals_map["Sales Ledger Control"]
        purchase_ledger_control = nominals_map["Purchase Ledger Control"]
        vat_control = nominals_map["Vat"]
        self.assertEqual(
            sales,
            {
                "nominal": "Sales",
                "total": Decimal('-100.00'),
                "parents": ["Revenues", "Revenue"],
                "ytd": Decimal("-100.00")
            }
        )
        self.assertEqual(
            sundry,
            {
                "nominal": "Sundry",
                "total": Decimal('100.00'),
                "parents": ["Expenses", "Expense"],
                "ytd": Decimal("100.00")
            }
        )
        self.assertEqual(
            sales_ledger_control,
            {
                "nominal": "Sales Ledger Control",
                "total": Decimal('120.00'),
                "parents": ["Assets", "Current Assets"],
                "ytd": Decimal("120.00")
            }
        )
        self.assertEqual(
            purchase_ledger_control,
            {
                "nominal": "Purchase Ledger Control",
                "total": Decimal('-120.00'),
                "parents": ["Liabilities", "Current Liabilities"],
                "ytd": Decimal("-120.00")
            }
        )
        self.assertEqual(
            vat_control,
            {
                "nominal": "Vat",
                "total": Decimal('0.00'),
                "parents": ["Liabilities", "Current Liabilities"],
                "ytd": Decimal("0.00")
            }
        )

    def test_different_fy(self):
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={
                "from_period": self.p_201912.pk,
                "to_period": self.p_202001.pk
            }
        )
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "Period range must be within the same FY"
        )

    def test_same_fy_but_invalid_period_range(self):
        self.client.force_login(self.user)
        response = self.client.get(
            self.url,
            data={
                "from_period": self.p_202002.pk,
                "to_period": self.p_202001.pk
            }
        )
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "<li>Invalid period range.  Period From cannot be after Period To</li>"
        )
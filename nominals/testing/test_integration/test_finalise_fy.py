from datetime import date

from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction
from nominals.views import FinaliseFY


class FinaliseFYTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.fy_2019 = fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=12)
        cls.p_201901 = p_201901 = Period.objects.create(
            fy=fy_2019, period="01", fy_and_period="201901", month_end=date(2019, 1, 31))

        cls.fy_2020 = fy_2020 = FinancialYear.objects.create(
            financial_year=2020, number_of_periods=12)
        cls.p_202001 = p_202001 = Period.objects.create(
            fy=fy_2020, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))
        cls.p_202002 = p_202002 = Period.objects.create(
            fy=fy_2020, period="02", fy_and_period="202002", month_end=date(2020, 2, 29))

        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.url = reverse("nominals:finalise_fy")

        # P/L
        cls.revenue_1 = revenue_1 = Nominal.objects.create(
            name="revenue", type="pl")
        cls.revenue_2 = revenue_2 = Nominal.objects.create(
            name="revenue", type="pl", parent=revenue_1)
        cls.sales = sales = Nominal.objects.create(
            name="sales", type="pl", parent=revenue_2)

        # Expenses
        cls.expenses_1 = expenses_1 = Nominal.objects.create(
            name="expenses", type="pl")
        cls.expenses_2 = expenses_2 = Nominal.objects.create(
            name="expenses", type="pl", parent=expenses_1)
        cls.staff = staff = Nominal.objects.create(
            name="staff", type="pl", parent=expenses_2)

        # ASSETS
        assets = Nominal.objects.create(name="Assets", type="b")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets", type="b")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account", type="b")
        cls.debtors_nominal = Nominal.objects.create(
            parent=current_assets, name="Trade Debtors", type="b")

        # LIABILITIES
        cls.liabilities = liabilities = Nominal.objects.create(
            name="Liabilities", type="b"
        )
        cls.current_liabilities = current_liabilities = Nominal.objects.create(
            name="Current Liabilities", type="b", parent=liabilities
        )
        cls.vat_output = vat_output = Nominal.objects.create(
            name="Vat Output", type="b", parent=current_liabilities
        )

        # EQUITY
        cls.equity_1 = equity_1 = Nominal.objects.create(
            name="Equity", type="b")
        cls.equity_2 = equity_2 = Nominal.objects.create(
            name="Equity", type="b", parent=equity_1)
        cls.retained_earnings = retained_earnings = Nominal.objects.create(
            name="Retained Earnings",
            type="b",
            parent=equity_2
        )

    def test_finalising_first_fy(self):
        # all module periods still in FY being finalised
        module_settings = ModuleSettings.objects.create(
            cash_book_period=self.p_201901,
            nominals_period=self.p_201901,
            purchases_period=self.p_201901,
            sales_period=self.p_201901
        )

        t1 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=1,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="g",
            type="pi",
            nominal=self.staff,
            value=1000
        )
        t2 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=2,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="v",
            type="pi",
            nominal=self.vat_output,
            value=200
        )
        t3 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=3,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="t",
            type="pi",
            nominal=self.debtors_nominal,
            value=-1200
        )
        self.client.force_login(self.user)
        response = self.client.post(
            self.url, data={"financial_year": self.fy_2019.pk})
        self.assertEqual(
            response.status_code,
            302
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            6
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )
        self.assertEqual(
            nom_trans[2],
            t3
        )

        nom_trans = nom_trans[3:]
        for t in nom_trans:
            if t.nominal == self.debtors_nominal:
                debtors_bf = t
            elif t.nominal == self.vat_output:
                vat_output_bf = t
            elif t.nominal == self.retained_earnings:
                retained_earnings_bf = t

        self.assertEqual(
            debtors_bf.module,
            "NL"
        )
        self.assertEqual(
            debtors_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            debtors_bf.period,
            self.p_202001
        )
        self.assertEqual(
            debtors_bf.field,
            "t"
        )
        self.assertEqual(
            debtors_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtors_bf.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            debtors_bf.value,
            -1200
        )

        self.assertEqual(
            vat_output_bf.module,
            "NL"
        )
        self.assertEqual(
            vat_output_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            vat_output_bf.period,
            self.p_202001
        )
        self.assertEqual(
            vat_output_bf.field,
            "t"
        )
        self.assertEqual(
            vat_output_bf.type,
            "nbf"
        )
        self.assertEqual(
            vat_output_bf.nominal,
            self.vat_output
        )
        self.assertEqual(
            vat_output_bf.value,
            200
        )

        self.assertEqual(
            retained_earnings_bf.module,
            "NL"
        )
        self.assertEqual(
            retained_earnings_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            retained_earnings_bf.period,
            self.p_202001
        )
        self.assertEqual(
            retained_earnings_bf.field,
            "t"
        )
        self.assertEqual(
            retained_earnings_bf.type,
            "nbf"
        )
        self.assertEqual(
            retained_earnings_bf.nominal,
            self.retained_earnings
        )
        self.assertEqual(
            retained_earnings_bf.value,
            1000
        )

        module_settings = ModuleSettings.objects.first()
        self.assertEqual(
            module_settings.cash_book_period,
            self.p_202001
        )
        self.assertEqual(
            module_settings.nominals_period,
            self.p_202001
        )
        self.assertEqual(
            module_settings.purchases_period,
            self.p_202001
        )
        self.assertEqual(
            module_settings.sales_period,
            self.p_202001
        )

    def test_finalising_first_fy_when_already_in_next_year(self):
        module_settings = ModuleSettings.objects.create(
            cash_book_period=self.p_202002,
            nominals_period=self.p_202002,
            purchases_period=self.p_202002,
            sales_period=self.p_202002
        )

        t1 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=1,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="g",
            type="pi",
            nominal=self.staff,
            value=1000
        )
        t2 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=2,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="v",
            type="pi",
            nominal=self.vat_output,
            value=200
        )
        t3 = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=3,
            date=date.today(),
            ref="1",
            period=self.p_201901,
            field="t",
            type="pi",
            nominal=self.debtors_nominal,
            value=-1200
        )
        self.client.force_login(self.user)
        response = self.client.post(
            self.url, data={"financial_year": self.fy_2019.pk})
        self.assertEqual(
            response.status_code,
            302
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            6
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )
        self.assertEqual(
            nom_trans[2],
            t3
        )

        nom_trans = nom_trans[3:]
        for t in nom_trans:
            if t.nominal == self.debtors_nominal:
                debtors_bf = t
            elif t.nominal == self.vat_output:
                vat_output_bf = t
            elif t.nominal == self.retained_earnings:
                retained_earnings_bf = t

        self.assertEqual(
            debtors_bf.module,
            "NL"
        )
        self.assertEqual(
            debtors_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            debtors_bf.period,
            self.p_202001
        )
        self.assertEqual(
            debtors_bf.field,
            "t"
        )
        self.assertEqual(
            debtors_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtors_bf.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            debtors_bf.value,
            -1200
        )

        self.assertEqual(
            vat_output_bf.module,
            "NL"
        )
        self.assertEqual(
            vat_output_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            vat_output_bf.period,
            self.p_202001
        )
        self.assertEqual(
            vat_output_bf.field,
            "t"
        )
        self.assertEqual(
            vat_output_bf.type,
            "nbf"
        )
        self.assertEqual(
            vat_output_bf.nominal,
            self.vat_output
        )
        self.assertEqual(
            vat_output_bf.value,
            200
        )

        self.assertEqual(
            retained_earnings_bf.module,
            "NL"
        )
        self.assertEqual(
            retained_earnings_bf.ref,
            "YEAR END 2019"
        )
        self.assertEqual(
            retained_earnings_bf.period,
            self.p_202001
        )
        self.assertEqual(
            retained_earnings_bf.field,
            "t"
        )
        self.assertEqual(
            retained_earnings_bf.type,
            "nbf"
        )
        self.assertEqual(
            retained_earnings_bf.nominal,
            self.retained_earnings
        )
        self.assertEqual(
            retained_earnings_bf.value,
            1000
        )

        # check that the module periods have not been changed
        module_settings = ModuleSettings.objects.first()
        self.assertEqual(
            module_settings.cash_book_period,
            self.p_202002
        )
        self.assertEqual(
            module_settings.nominals_period,
            self.p_202002
        )
        self.assertEqual(
            module_settings.purchases_period,
            self.p_202002
        )
        self.assertEqual(
            module_settings.sales_period,
            self.p_202002
        )

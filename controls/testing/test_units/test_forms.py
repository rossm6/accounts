from datetime import date

from controls.forms import ModuleSettingsForm
from controls.models import FinancialYear, ModuleSettings, Period
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction


class ModuleSettingsTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        # create 2019
        fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=12)
        periods = []
        for i in range(1, 13):
            periods.append(
                Period(
                    fy=fy_2019,
                    fy_and_period="2019" + str(i).rjust(2, "0"),
                    period=str(i).rjust(2, "0"),
                    month_start=date(2019, i, 1)
                )
            )
        p_2019 = Period.objects.bulk_create(periods)
        cls.p_201901 = fy_2019.first_period()
        # create 2020
        fy_2020 = FinancialYear.objects.create(
            financial_year=2020, number_of_periods=12)
        periods = []
        for i in range(1, 13):
            periods.append(
                Period(
                    fy=fy_2020,
                    fy_and_period="2020" + str(i).rjust(2, "0"),
                    period=str(i).rjust(2, "0"),
                    month_start=date(2020, i, 1)
                )
            )
        p_2020 = Period.objects.bulk_create(periods)
        cls.p_202001 = fy_2020.first_period()
        # create 2021
        cls.fy_2021 = fy_2021 = FinancialYear.objects.create(
            financial_year=2021, number_of_periods=12)
        periods = []
        for i in range(1, 13):
            periods.append(
                Period(
                    fy=fy_2021,
                    fy_and_period="2021" + str(i).rjust(2, "0"),
                    period=str(i).rjust(2, "0"),
                    month_start=date(2021, i, 1)
                )
            )
        p_2021 = Period.objects.bulk_create(periods)
        cls.p_202101 = fy_2021.first_period()
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

    def test_queryset_when_no_fy_finalised(self):
        m = ModuleSettings.objects.create(
            cash_book_period=None, nominals_period=None, purchases_period=None, sales_period=None)
        q = list(Period.objects.all())
        f = ModuleSettingsForm(instance=m)
        self.assertEqual(
            list(f.fields["cash_book_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["nominals_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["purchases_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["sales_period"].queryset),
            q
        )

    def test_queryset_when_a_fy_is_finalised(self):
        # only 2021 is not finalised
        # 2019
        bf_2019_1 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref="YEAR END 2018",
            period=self.p_201901,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=1000
        )
        bf_2019_2 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=2,
            date=date.today(),
            ref="YEAR END 2018",
            period=self.p_201901,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )
        # 2020
        bf_2020_1 = NominalTransaction.objects.create(
            module="NL",
            header=2,
            line=1,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=1000
        )
        bf_2020_2 = NominalTransaction.objects.create(
            module="NL",
            header=2,
            line=2,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )
        m = ModuleSettings.objects.create(
            cash_book_period=None, nominals_period=None, purchases_period=None, sales_period=None)
        q = list(Period.objects.filter(fy_and_period__gte=self.p_202001.fy_and_period))
        f = ModuleSettingsForm(instance=m)
        self.assertEqual(
            list(f.fields["cash_book_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["nominals_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["purchases_period"].queryset),
            q
        )
        self.assertEqual(
            list(f.fields["sales_period"].queryset),
            q
        )

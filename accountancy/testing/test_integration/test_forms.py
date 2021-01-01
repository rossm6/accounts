from datetime import date

from controls.models import FinancialYear, ModuleSettings, Period
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction
from purchases.forms import PurchaseHeaderForm


class BaseTransactionHeaderFormTests(TestCase):
    """
    Use PurchaseHeaderForm has an example subclass of BaseTransactionHeaderForm
    Base class is not valid on it's own because it inherits from ModelForm but does not have a Meta attribute
    """

    @classmethod
    def setUpTestData(cls):
        cls.m = m = ModuleSettings.objects.create(
            cash_book_period=None, nominals_period=None, purchases_period=None, sales_period=None)
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

    def test_no_periods(self):
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            0
        )

    def test_no_fy_finalised_earliest_period(self):
        self.m.purchases_period = self.p_201901
        self.m.save()
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            2
        )
        self.assertEqual(
            str(q[0]),
            "01 2019"
        )
        self.assertEqual(
            str(q[1]),
            "02 2019"
        )

    def test_no_fy_finalised_in_between_period(self):
        self.m.purchases_period = Period.objects.get(fy_and_period="201906")
        self.m.save()
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            3
        )
        self.assertEqual(
            str(q[0]),
            "05 2019"
        )
        self.assertEqual(
            str(q[1]),
            "06 2019"
        )
        self.assertEqual(
            str(q[2]),
            "07 2019"
        )

    def test_no_finalised_latest_period(self):
        self.m.purchases_period = Period.objects.get(fy_and_period="202112")
        self.m.save()
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            2
        )
        self.assertEqual(
            str(q[0]),
            "11 2021"
        )
        self.assertEqual(
            str(q[1]),
            "12 2021"
        )

    def test_fy_finalised_earliest_period(self):
        self.m.purchases_period = Period.objects.get(fy_and_period="202001")
        self.m.save()
        NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=100
        )
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            2
        )
        self.assertEqual(
            str(q[0]),
            "01 2020"
        )
        self.assertEqual(
            str(q[1]),
            "02 2020"
        )

    def test_fy_finalised_in_between_period(self):
        self.m.purchases_period = Period.objects.get(fy_and_period="202006")
        self.m.save()
        NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=100
        )
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            3
        )
        self.assertEqual(
            str(q[0]),
            "05 2020"
        )
        self.assertEqual(
            str(q[1]),
            "06 2020"
        )
        self.assertEqual(
            str(q[2]),
            "07 2020"
        )

    def test_fy_finalised_latest_period_in_fy(self):
        self.m.purchases_period = Period.objects.get(fy_and_period="202012")
        self.m.save()
        NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=100
        )
        f = PurchaseHeaderForm(contact_model_name="supplier")
        q = f.fields["period"].queryset
        q = list(q)
        self.assertEqual(
            len(q),
            3
        )
        self.assertEqual(
            str(q[0]),
            "11 2020"
        )
        self.assertEqual(
            str(q[1]),
            "12 2020"
        )
        self.assertEqual(
            str(q[2]),
            "01 2021"
        )
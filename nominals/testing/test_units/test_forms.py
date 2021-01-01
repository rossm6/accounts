from json import loads
from datetime import date

from controls.models import FinancialYear, Period
from django.test import TestCase
from nominals.forms import FinaliseFYForm
from nominals.models import Nominal, NominalTransaction


class FinaliseFYFormTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        pass

    def test_when_there_are_no_fys(self):
        f = FinaliseFYForm()
        self.assertEqual(
            len(f.fields["financial_year"].queryset),
            0
        )
        self.assertEqual(
            f.initial,
            {}
        )

        bound_form = FinaliseFYForm(data={"financial_year": ""})
        self.assertFalse(
            bound_form.is_valid()
        )
        # so if there are no FYs the form will not be considered valid


    def test_queryset_when_no_finalised_years(self):
        FinancialYear.objects.create(financial_year=2019, number_of_periods=12)
        FinancialYear.objects.create(financial_year=2020, number_of_periods=12)
        fy_2018 = FinancialYear.objects.create(
            financial_year=2018, number_of_periods=12)
        f = FinaliseFYForm()
        q = f.fields["financial_year"].queryset
        self.assertEqual(
            len(q),
            1
        )
        self.assertEqual(
            q[0],
            fy_2018
        )
        self.assertEqual(
            f.initial,
            {
                "financial_year": fy_2018
            }
        )

    def test_queryset_with_multiple_finalised_and_not_finalised_years(self):
        test_nominal = Nominal.objects.create(name="test", type="pl")

        fy_2018 = FinancialYear.objects.create(
            financial_year=2018, number_of_periods=12)
        fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=12)
        p_201901 = Period.objects.create(
            fy=fy_2019, period="01", fy_and_period="201901", month_start=date(2019, 1, 31))
        fy_2020 = FinancialYear.objects.create(
            financial_year=2020, number_of_periods=12)
        p_202001 = Period.objects.create(
            fy=fy_2020, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        fy_2021 = FinancialYear.objects.create(
            financial_year=2021, number_of_periods=12)

        NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            ref="1",
            type="nbf",
            date=date.today(),
            field="t",
            nominal=test_nominal,
            value=100,
            period=p_201901
        )
        NominalTransaction.objects.create(
            module="NL",
            header=2,
            line=1,
            ref="1",
            type="nbf",
            date=date.today(),
            field="t",
            nominal=test_nominal,
            value=100,
            period=p_202001
        )

        f = FinaliseFYForm()
        q = f.fields["financial_year"].queryset
        self.assertEqual(
            len(q),
            1
        )
        self.assertEqual(
            q[0],
            fy_2020
        )
        self.assertEqual(
            f.initial,
            {
                "financial_year": fy_2020
            }
        )

    def test_next_year_is_missing(self):
        fy_2018 = FinancialYear.objects.create(
            financial_year=2018, number_of_periods=12)
        f = FinaliseFYForm(data={"financial_year": fy_2018.pk})
        self.assertFalse(f.is_valid())
        errors = f.errors.as_json()
        errors = loads(errors)
        self.assertEqual(
            len(errors.keys()),
            1
        )
        self.assertEqual(
            len(errors["__all__"]),
            1
        )
        self.assertEqual(
            errors["__all__"][0]["message"],
            "Cannot finalise this year because there isn't another to move into.  <a href='/controls/financial_year/create'>Create next FY</a></p>",
        )
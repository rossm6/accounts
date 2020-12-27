from datetime import date

from controls.forms import ModuleSettingsForm
from controls.models import FinancialYear, ModuleSettings, Period
from django.test import TestCase


class ModuleSettingsTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        # create 2019
        fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=12)
        periods = []
        for i in range(12):
            periods.append(
                Period(
                    fy=fy_2019,
                    fy_and_period="2019" + str(i).rjust(2, "0"),
                    period=str(i+1).rjust(2, "0"),
                    month_end=date(2019, i+1, 1)
                )
            )
        p_2019 = Period.objects.bulk_create(periods)
        # create 2020
        fy_2020 = FinancialYear.objects.create(
            financial_year=2020, number_of_periods=12)
        periods = []
        for i in range(12):
            periods.append(
                Period(
                    fy=fy_2020,
                    fy_and_period="2020" + str(i).rjust(2, "0"),
                    period=str(i+1).rjust(2, "0"),
                    month_end=date(2020, i+1, 1)
                )
            )
        p_2020 = Period.objects.bulk_create(periods)

    def test_queryset(self):
        period = Period.objects.get(fy_and_period="202001")
        m = ModuleSettings.objects.create(nominals_period=period)
        q = list(Period.objects.filter(fy__financial_year__gte=2020))
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

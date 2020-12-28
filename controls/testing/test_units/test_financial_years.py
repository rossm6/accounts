from datetime import date

from controls.exceptions import MissingPeriodError
from controls.models import FinancialYear, Period
from django.test import TestCase


class FinancialYearTests(TestCase):
    
    @classmethod
    def setUpTestData(cls):
        cls.fy = fy_2020 = FinancialYear.objects.create(financial_year=2020, number_of_periods=12)
        periods = []
        for i in range(12):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2020{p}",
                    month_end=date(2020,1,31), # does not matter,
                    fy=fy_2020
                )
            )
        Period.objects.bulk_create(periods)
        cls.fy_without_periods = FinancialYear.objects.create(financial_year=2021, number_of_periods=12)

    def test_first_period_successful(self):
        period = self.fy.first_period()
        self.assertEqual(
            period.period,
            "01"
        )
        self.assertEqual(
            period.fy_and_period,
            "202001"
        )

    def test_first_period_failure(self):
        with self.assertRaises(MissingPeriodError) as ctx:
            self.fy_without_periods.first_period()
        self.assertEqual(str(ctx.exception), "No periods found for this year")

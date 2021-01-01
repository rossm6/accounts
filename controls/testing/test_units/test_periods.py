from datetime import date

from controls.exceptions import MissingPeriodError
from controls.models import FinancialYear, Period
from django.test import TestCase


class PeriodSubTractTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        fy_2018 = FinancialYear.objects.create(financial_year=2018, number_of_periods=12)
        periods = []
        for i in range(12):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2018{p}",
                    month_start=date(2018,1,31), # does not matter,
                    fy=fy_2018
                )
            )
        Period.objects.bulk_create(periods)
        fy_2019 = FinancialYear.objects.create(financial_year=2019, number_of_periods=18)
        periods = []
        for i in range(18):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2019{p}",
                    month_start=date(2019,1,31), # does not matter,
                    fy=fy_2019
                )
            )
        Period.objects.bulk_create(periods)
        fy_2020 = FinancialYear.objects.create(financial_year=2020, number_of_periods=12)
        periods = []
        for i in range(12):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2020{p}",
                    month_start=date(2020,1,31), # does not matter,
                    fy=fy_2020
                )
            )
        Period.objects.bulk_create(periods)

    def test_ordering(self):
        periods = Period.objects.all()
        for i in range(len(periods) - 1):
            if periods[i].fy_and_period >= periods[i+1].fy_and_period:
                self.fail("Periods not order in ascending order based on fy_and_period")  

    def test_subtract_less_than_current_period(self):
        periods = list(Period.objects.all())
        last = periods[-1]
        penultimate = periods[-2]
        self.assertEqual(
            last - 1,
            penultimate
        )

    def test_subtract_number_same_as_period(self):
        periods = list(Period.objects.all())
        last = periods[-1]
        fy_2019_period_18 = periods[-13]
        self.assertEqual(
            last - 12,
            fy_2019_period_18
        )

    def test_subtract_periods_greater_than_period(self):
        periods = list(Period.objects.all())
        last = periods[-1]
        fy_2018_period_1 = periods[0]
        self.assertEqual(
            last - 41,
            fy_2018_period_1
        )

    def test_missing_fy_exception_for_subtracting_greater_than(self):
        first_period = Period.objects.first()
        with self.assertRaises(MissingPeriodError) as ctx:
            first_period - 3
        self.assertEqual(str(ctx.exception), "Previous FY with periods is missing")

    def test_missing_fy_exception_for_subtracting_same_as_period(self):
        first_period = Period.objects.first()
        with self.assertRaises(MissingPeriodError) as ctx:
            first_period - 1
        self.assertEqual(str(ctx.exception), "Previous FY with periods is missing")


class PeriodAdditionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        fy_2018 = FinancialYear.objects.create(financial_year=2018, number_of_periods=12)
        periods = []
        for i in range(12):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2018{p}",
                    month_start=date(2018,1,31), # does not matter,
                    fy=fy_2018
                )
            )
        Period.objects.bulk_create(periods)
        fy_2019 = FinancialYear.objects.create(financial_year=2019, number_of_periods=18)
        periods = []
        for i in range(18):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2019{p}",
                    month_start=date(2019,1,31), # does not matter,
                    fy=fy_2019
                )
            )
        Period.objects.bulk_create(periods)
        fy_2020 = FinancialYear.objects.create(financial_year=2020, number_of_periods=12)
        periods = []
        for i in range(12):
            p = f"{i+1}".rjust(2, "0")
            periods.append(
                Period(
                    period=p,
                    fy_and_period=f"2020{p}",
                    month_start=date(2020,1,31), # does not matter,
                    fy=fy_2020
                )
            )
        Period.objects.bulk_create(periods)

    def test_ordering(self):
        periods = Period.objects.all()
        for i in range(len(periods) - 1):
            if periods[i].fy_and_period >= periods[i+1].fy_and_period:
                self.fail("Periods not order in ascending order based on fy_and_period")  

    def test_addition_is_less_than_remaining_periods_in_year(self):
        periods = list(Period.objects.all())
        first = periods[0]
        fourth = periods[3]
        self.assertEqual(
            first + 3,
            fourth
        )

    def test_addition_is_equal_to_remaining_periods_in_year(self):
        periods = list(Period.objects.all())
        fy_2019_period_1 = periods[12]
        fy_2019_period_18 = periods[12 + 17]
        self.assertEqual(
            fy_2019_period_1 + 17,
            fy_2019_period_18
        )

    def test_addition_is_greater_than_remaining_periods(self):
        periods = list(Period.objects.all())
        fy_2018_period_1 = periods[0]
        fy_2020_period_12 = periods[-1]
        self.assertEqual(
            fy_2018_period_1 + 41,
            fy_2020_period_12
        )

    def test_missing_fy_exception_1(self):
        last_period = Period.objects.last()
        with self.assertRaises(MissingPeriodError) as ctx:
            last_period + 1
        self.assertEqual(str(ctx.exception), "Next FY with periods is missing")



class PeriodOverloadOperatorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        fy_2018 = FinancialYear.objects.create(financial_year=2018, number_of_periods=12)
        cls.p1 = Period.objects.create(
            period="01",
            fy_and_period="201801",
            month_start=date(2018,1,31), # does not matter
            fy=fy_2018
        )
        cls.p2 = Period.objects.create(
            period="02",
            fy_and_period="201802",
            month_start=date(2018,1,31), # does not matter
            fy=fy_2018
        )
        cls.p3 = Period.objects.create(
            period="03",
            fy_and_period="201803",
            month_start=date(2018,1,31), # does not matter
            fy=fy_2018
        )

    def test_le_less_than(self):
        self.assertTrue(
            self.p1 <= self.p2
        )

    def test_le_equal(self):
        self.assertTrue(
            self.p1 <= self.p1
        )

    def test_le_not(self):
        self.assertFalse(
            self.p2 <= self.p1
        )

    def test_lt(self):
        self.assertTrue(
            self.p1 < self.p2
        )

    def test_lt_not(self):
        self.assertFalse(
            self.p2 < self.p1
        )

    def test_ge_greater_than(self):
        self.assertTrue(
            self.p2 >= self.p1 
        )

    def test_ge_equal(self):
        self.assertTrue(
            self.p1 >= self.p1 
        )

    def test_ge_not(self):
        self.assertFalse(
            self.p1 >= self.p2
        )

    def test_gt(self):
        self.assertTrue(
            self.p2 >= self.p1
        )

    def test_gt_not(self):
        self.assertFalse(
            self.p1 >= self.p2
        )
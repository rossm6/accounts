from datetime import date

from controls.models import FinancialYear, Period
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction


class CreateFyTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("controls:fy_create")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")

    def test_successful(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, data={
            "financial_year": 2020,
            "period-0-month_end": "01-2020",
            "period-1-month_end": "02-2020",
            "period-2-month_end": "03-2020",
            "period-3-month_end": "04-2020",
            "period-4-month_end": "05-2020",
            "period-5-month_end": "06-2020",
            "period-6-month_end": "07-2020",
            "period-7-month_end": "08-2020",
            "period-8-month_end": "09-2020",
            "period-9-month_end": "10-2020",
            "period-10-month_end": "11-2020",
            "period-11-month_end": "12-2020",
            "period-TOTAL_FORMS": "12",
            "period-INITIAL_FORMS": "0",
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        self.assertEqual(
            response.status_code,
            302
        )
        fys = FinancialYear.objects.all()
        self.assertEqual(
            len(fys),
            1
        )
        fy = fys[0]
        self.assertEqual(
            fy.financial_year,
            2020
        )
        self.assertEqual(
            fy.number_of_periods,
            12
        )
        periods = Period.objects.all()
        self.assertEqual(
            len(periods),
            12
        )
        for i, period in enumerate(periods):
            self.assertEqual(
                period.fy,
                fy
            )
            self.assertEqual(
                period.month_end,
                date(2020, i + 1, 1)
            )
            self.assertEqual(
                period.period,
                str(i + 1).rjust(2, "0")
            )
            self.assertEqual(
                period.fy_and_period,
                str(fy) + str(i+1).rjust(2, "0")
            )

    def test_failure_when_fys_are_not_consecutive(self):
        self.client.force_login(self.user)
        FinancialYear.objects.create(financial_year=2018, number_of_periods=12)
        response = self.client.post(self.url, data={
            "financial_year": 2020,
            "period-0-month_end": "01-2020",
            "period-1-month_end": "02-2020",
            "period-2-month_end": "03-2020",
            "period-3-month_end": "04-2020",
            "period-4-month_end": "05-2020",
            "period-5-month_end": "06-2020",
            "period-6-month_end": "07-2020",
            "period-7-month_end": "08-2020",
            "period-8-month_end": "09-2020",
            "period-9-month_end": "10-2020",
            "period-10-month_end": "11-2020",
            "period-11-month_end": "12-2020",
            "period-TOTAL_FORMS": "12",
            "period-INITIAL_FORMS": "0",
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "<li>Financial years must be consecutive.  The earliest is 2018 and the latest is 2018</li>"
        )
        self.assertEqual(
            len(
                FinancialYear.objects.all()
            ),
            1
        )
        self.assertEqual(
            len(
                Period.objects.all()
            ),
            0
        )

    def test_failure_when_period_does_have_month_end(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, data={
            "financial_year": 2020,
            "period-0-month_end": "01-2020",
            "period-1-month_end": "02-2020",
            "period-2-month_end": "03-2020",
            "period-3-month_end": "04-2020",
            "period-4-month_end": "05-2020",
            "period-5-month_end": "06-2020",
            "period-6-month_end": "07-2020",
            "period-7-month_end": "08-2020",
            "period-8-month_end": "09-2020",
            "period-9-month_end": "10-2020",
            "period-10-month_end": "11-2020",
            "period-11-month_end": "",
            "period-TOTAL_FORMS": "12",
            "period-INITIAL_FORMS": "0",
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "<li>All periods you wish to create must have a month selected.  Delete any unwanted periods otherwise</li>"
        )

    def test_failure_when_month_ends_are_not_consecutive(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, data={
            "financial_year": 2020,
            "period-0-month_end": "01-2020",
            "period-1-month_end": "02-2020",
            "period-2-month_end": "03-2020",
            "period-3-month_end": "04-2020",
            "period-4-month_end": "05-2020",
            "period-5-month_end": "06-2020",
            "period-6-month_end": "07-2020",
            "period-7-month_end": "08-2020",
            "period-8-month_end": "09-2020",
            "period-9-month_end": "10-2020",
            "period-10-month_end": "11-2020",
            "period-11-month_end": "01-2021",
            "period-TOTAL_FORMS": "12",
            "period-INITIAL_FORMS": "0",
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "<li>Periods must be consecutive calendar months</li>"
        )

    def test_failure_when_months_across_all_fys_are_not_consecutive(self):
        self.client.force_login(self.user)
        fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=1)
        p = Period.objects.create(
            fy=fy_2019, fy_and_period="201901", period="01", month_end=date(2020, 1, 1))
        response = self.client.post(self.url, data={
            "financial_year": 2020,
            "period-0-month_end": "01-2020",
            "period-1-month_end": "02-2020",
            "period-2-month_end": "03-2020",
            "period-3-month_end": "04-2020",
            "period-4-month_end": "05-2020",
            "period-5-month_end": "06-2020",
            "period-6-month_end": "07-2020",
            "period-7-month_end": "08-2020",
            "period-8-month_end": "09-2020",
            "period-9-month_end": "10-2020",
            "period-10-month_end": "11-2020",
            "period-11-month_end": "12-2020",
            "period-TOTAL_FORMS": "12",
            "period-INITIAL_FORMS": "0",
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            "<li>Period 01 of FY 2019 is for calendar month Jan 2020.  "
            "But you are trying to now create a period for calendar month Jan 2020 again.  "
            "This is not allowed because periods must be consecutive calendar months across ALL financial years.</li>"
        )


class AdjustFYTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("controls:fy_adjust")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
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

    def test_successful(self):
        self.client.force_login(self.user)
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
        periods = list(p_2019) + list(p_2020)
        second_half_of_2019 = periods[6:12]
        for p in second_half_of_2019:
            p.fy = fy_2020
        form_data = {}
        for i, p in enumerate(periods):
            form_data.update({
                "period-" + str(i) + "-id": p.pk,
                "period-" + str(i) + "-month_end": p.month_end.strftime("%m-%Y"),
                "period-" + str(i) + "-period": p.period,
                "period-" + str(i) + "-fy": p.fy_id
            })
        form_data.update({
            "period-TOTAL_FORMS": str(len(periods)),
            "period-INITIAL_FORMS": str(len(periods)),
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        response = self.client.post(self.url, data=form_data)
        self.assertEqual(
            response.status_code,
            302
        )
        fy_2019.refresh_from_db()
        fy_2020.refresh_from_db()
        periods = Period.objects.all()
        periods_2019 = periods[:6]
        for i, p in enumerate(periods_2019):
            p.fy = fy_2019
            p.month_end = date(2019, i+1, 1)
            p.fy_and_period = "2019" + str(i+1).rjust(2, "0")
            p.period = str(i+1).rjust(2, "0")
        periods_2020 = periods[6:]
        for i, p in enumerate(periods_2020):
            p.fy = fy_2020
            p.month_end = date(2019, 6, 1) + relativedelta(months=+i)
            p.fy_and_period = "2020" + str(i+1).rjust(2, "0")
            p.period = str(i+1).rjust(2, "0")
        self.assertEqual(
            fy_2019.number_of_periods,
            6
        )
        self.assertEqual(
            fy_2020.number_of_periods,
            18
        )

    def test_successful_when_bfs_are_present(self):
        """
        Say you have two FYs, each of 12 periods,
            2019
            2020

        If you extend 2019 to 18 months, 2019 and 2020 are affected by the
        change.

        If 2019 c/fs have already posted as b/fs into 2020 we need to delete
        these bfs and anyway bfs posted in periods after.
        """
        # create the fys and periods
        self.client.force_login(self.user)
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
        p_201901 = fy_2019.first_period()
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
        p_202001 = fy_2020.first_period()
        # post the bfs
        # 2019
        bf_2019_1 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref="YEAR END 2018",
            period=p_201901,
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
            period=p_201901,
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
            period=p_202001,
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
            period=p_202001,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )
        # prepare for adjusting FY
        periods = list(p_2019) + list(p_2020)
        second_half_of_2019 = periods[6:12]
        for p in second_half_of_2019:
            p.fy = fy_2020
        form_data = {}
        for i, p in enumerate(periods):
            form_data.update({
                "period-" + str(i) + "-id": p.pk,
                "period-" + str(i) + "-month_end": p.month_end.strftime("%m-%Y"),
                "period-" + str(i) + "-period": p.period,
                "period-" + str(i) + "-fy": p.fy_id
            })
        form_data.update({
            "period-TOTAL_FORMS": str(len(periods)),
            "period-INITIAL_FORMS": str(len(periods)),
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        # now adjust via the view
        response = self.client.post(self.url, data=form_data)
        self.assertEqual(
            response.status_code,
            302
        )
        fy_2019.refresh_from_db()
        fy_2020.refresh_from_db()
        periods = Period.objects.all()
        periods_2019 = periods[:6]
        for i, p in enumerate(periods_2019):
            p.fy = fy_2019
            p.month_end = date(2019, i+1, 1)
            p.fy_and_period = "2019" + str(i+1).rjust(2, "0")
            p.period = str(i+1).rjust(2, "0")
        periods_2020 = periods[6:]
        for i, p in enumerate(periods_2020):
            p.fy = fy_2020
            p.month_end = date(2019, 6, 1) + relativedelta(months=+i)
            p.fy_and_period = "2020" + str(i+1).rjust(2, "0")
            p.period = str(i+1).rjust(2, "0")
        self.assertEqual(
            fy_2019.number_of_periods,
            6
        )
        self.assertEqual(
            fy_2020.number_of_periods,
            18
        )
        # check that the b/fs posted to 01 2020 have been deleted i.e. 2020 has been rolled back
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            nom_trans[0],
            bf_2019_1
        )
        self.assertEqual(
            nom_trans[1],
            bf_2019_2
        )



    def test_failure_when_FY_does_contain_consecutive_periods(self):
        self.client.force_login(self.user)
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
        periods = list(p_2019) + list(p_2020)
        second_half_of_2019 = periods[6:12]
        for p in second_half_of_2019:
            p.fy = fy_2020
        second_half_of_2019[2].fy = fy_2019
        form_data = {}
        for i, p in enumerate(periods):
            form_data.update({
                "period-" + str(i) + "-id": p.pk,
                "period-" + str(i) + "-month_end": p.month_end.strftime("%m-%Y"),
                "period-" + str(i) + "-period": p.period,
                "period-" + str(i) + "-fy": p.fy_id
            })
        form_data.update({
            "period-TOTAL_FORMS": str(len(periods)),
            "period-INITIAL_FORMS": str(len(periods)),
            "period-MIN_NUM_FORMS": "0",
            "period-MAX_NUM_FORMS": "1000"
        })
        response = self.client.post(self.url, data=form_data)
        self.assertEqual(
            response.status_code,
            200
        )

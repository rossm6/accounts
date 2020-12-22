from datetime import date

from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from purchases.models import PurchaseHeader, Supplier


class AgedCreditorReportTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code='1', name='1')
        cls.url = reverse("purchases:creditors_report")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_void_is_excluded(self):
        self.client.force_login(self.user)
        voided_payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=-100,
            total=-100,
            paid=0,
            status="v"
        )
        q = {}
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
            

    def test_payment_is_in_allocated(self):
        self.client.force_login(self.user)
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=-100,
            total=-100,
            paid=0,
            status="c"
        )
        q = {}
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )


    def test_invoice_current_debt(self):
        self.client.force_login(self.user)

    def test_invoice_1_month_old_debt(self):
        self.client.force_login(self.user)

    def test_invoice_2_month_old_debt(self):
        self.client.force_login(self.user)

    def test_invoice_3_month_old_debt(self):
        self.client.force_login(self.user)

    def test_invoice_4_month_old_debt(self):
        self.client.force_login(self.user)

    def test_invoice_with_mawhere_invoice_is_matched_by(self):
        self.client.force_login(self.user)

    def test_unmatching_where_is_matched_to(self):
        self.client.force_login(self.user)

    def test_unmatching_where_is_matched_by(self):
        self.client.force_login(self.user)

    def test_missing_previous_periods(self):
        self.client.force_login(self.user)

    def test_missing_future_periods(self):
        self.client.force_login(self.user)

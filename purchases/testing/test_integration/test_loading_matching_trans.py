import json
from datetime import date

from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from purchases.models import PurchaseHeader, PurchaseMatching, Supplier


class LoadingMatchingTransactions(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code='1', name='1')
        cls.url = reverse("purchases:load_matching_transactions")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_returns_tran(self):
        header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            status="c"
        )
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={"s": self.supplier.name}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        json_content = json.loads(content)
        self.assertEqual(
            json_content["recordsTotal"],
            1
        )
        self.assertEqual(
            json_content["recordsFiltered"],
            1
        )
        self.assertEqual(
            len(json_content["data"]),
            1
        )

    def test_excludes_void(self):
        header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            status="v"
        )
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={"s": self.supplier.name}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        json_content = json.loads(content)
        self.assertEqual(
            json_content["recordsTotal"],
            1
        )
        self.assertEqual(
            json_content["recordsFiltered"],
            0
        )
        self.assertEqual(
            len(json_content["data"]),
            0
        )

    def test_not_outstanding_is_excluded(self):
        header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=0,
            paid=100,
            total=100,
            status="c"
        )
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={"s": self.supplier.name}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        json_content = json.loads(content)
        self.assertEqual(
            json_content["recordsTotal"],
            1
        )
        self.assertEqual(
            json_content["recordsFiltered"],
            0
        )
        self.assertEqual(
            len(json_content["data"]),
            0
        )

    def test_tran_itself_is_excluded(self):
        header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            paid=0,
            total=100,
            status="c"
        )
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={
                "s": self.supplier.name,
                "edit": header.pk,
            }, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        json_content = json.loads(content)
        self.assertEqual(
            json_content["recordsTotal"],
            1
        )
        self.assertEqual(
            json_content["recordsFiltered"],
            0
        )
        self.assertEqual(
            len(json_content["data"]),
            0
        )

    def test_already_matched_are_excluded(self):
        header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=50,
            paid=50,
            total=100,
            status="c"
        )
        matching_header = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=-50,
            paid=-50,
            total=-100,
            status="c"
        )
        match = PurchaseMatching.objects.create(
            matched_by=header,
            matched_to=matching_header,
            value=-50,
            matched_by_type="pi",
            matched_to_type="pi",
            period=self.period
        )
        self.client.force_login(self.user)
        response = self.client.get(
            self.url, 
            data={
                "s": self.supplier.name,
                "edit": header.pk,
            }, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        json_content = json.loads(content)
        self.assertEqual(
            json_content["recordsTotal"],
            2
        )
        self.assertEqual(
            json_content["recordsFiltered"],
            0
        )
        self.assertEqual(
            len(json_content["data"]),
            0
        )
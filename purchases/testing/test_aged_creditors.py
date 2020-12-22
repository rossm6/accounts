import json
from datetime import date

from accountancy.testing.helpers import dict_to_url
from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from purchases.models import PurchaseHeader, Supplier

DATE_OUTPUT_FORMAT = '%d %b %Y'

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
        # self.client.force_login(self.user)
        # voided_payment = PurchaseHeader.objects.create(
        #     type="pp",
        #     supplier=self.supplier,
        #     ref="1",
        #     period=self.period,
        #     date=date.today(),
        #     due_date=date.today(),
        #     due=-100,
        #     total=-100,
        #     paid=0,
        #     status="v"
        # )
        # q = {}
        # response = self.client.get(
        #     self.url + "?" + q,
        #     HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        # )
        pass

    def test_payment_is_in_allocated(self):
        # self.client.force_login(self.user)
        # payment = PurchaseHeader.objects.create(
        #     type="pp",
        #     supplier=self.supplier,
        #     ref="1",
        #     period=self.period,
        #     date=date.today(),
        #     due_date=date.today(),
        #     due=-100,
        #     total=-100,
        #     paid=0,
        #     status="c"
        # )
        # q = {}
        # response = self.client.get(
        #     self.url + "?" + q,
        #     HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        # )
        pass

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
        # any old transaction in the period being reported on will do
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
        d = {
            'draw': '1', 
            'columns': {
                0: {'data': 'supplier', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'unallocated', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'current', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': '1 month', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                8: {'data': '2 month', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                9: {'data': '3 month', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                10: {'data': '4 month', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {0: {'column': '0', 'dir': 'asc'}}, 
            'start': '0', 
            'length': '153', 
            'search': {'value': '', 'regex': 'false'}, 
            'from_supplier': '', 
            'to_supplier': '', 
            'period': f'{self.period.pk}', 
            'show_transactions': 'yes', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        print(data)
        # report is run for first period
        # check that 1 month debt and older each has zero value
        # in doing so we also check report does not error either
        self.assertEqual(
            data['draw'],
            1
        )
        self.assertEqual(
            data['recordsTotal'],
            1
        )
        self.assertEqual(
            data['recordsFiltered'],
            1
        )
        self.assertEqual(
            len(data['data']),
            1
        )

        d = data["data"][0]
        meta = d["meta"]
        self.assertEqual(
            meta["contact_pk"],
            self.supplier.pk
        )

        
        self.assertEqual(
            d["supplier"],
            str(self.supplier)
        )
        self.assertEqual(
            d["date"],
            payment.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            payment.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            payment.ref
        )
        self.assertEqual(
            d["total"],
            payment.ui_total
        )
        self.assertEqual(
            d["unallocated"],
            payment.ui_due
        )
        self.assertEqual(
            d["current"],
            0
        )
        self.assertEqual(
            d["1 month"],
            0
        )
        self.assertEqual(
            d["2 month"],
            0
        )
        self.assertEqual(
            d["3 month"],
            0
        )
        self.assertEqual(
            d["4 month"],
            0
        )

        DT_RowData = data["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )
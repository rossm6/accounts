import json
from datetime import date

from accountancy.testing.helpers import dict_to_url
from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from purchases.models import PurchaseHeader, PurchaseMatching, Supplier

DATE_OUTPUT_FORMAT = '%d %b %Y'


class AgedCreditorReportWithTransactionsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code='1', name='1')
        cls.url = reverse("purchases:creditors_report")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period_1 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        cls.period_2 = Period.objects.create(
            fy=fy, period="02", fy_and_period="202002", month_start=date(2020, 2, 29))
        cls.period_3 = Period.objects.create(
            fy=fy, period="03", fy_and_period="202003", month_start=date(2020, 3, 31))
        cls.period_4 = Period.objects.create(
            fy=fy, period="04", fy_and_period="202004", month_start=date(2020, 4, 30))
        cls.period_5 = Period.objects.create(
            fy=fy, period="05", fy_and_period="202005", month_start=date(2020, 5, 31))      

    def test_void_is_excluded(self):
        self.client.force_login(self.user)
        voided_payment = PurchaseHeader.objects.create(
                type="pp",
                supplier=self.supplier,
                ref="1",
                period=self.period_1,
                date=date.today(),
                due_date=None,
                due=-100,
                total=-100,
                paid=0,
                status="v"
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
            'period': f'{self.period_1.pk}', 
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
        self.assertEqual(
            data['draw'],
            1
        )
        self.assertEqual(
            data['recordsTotal'],
            0
        )
        self.assertEqual(
            data['recordsFiltered'],
            0
        )
        self.assertEqual(
            len(data['data']),
            0
        )

    def test_payment_is_in_unallocated(self):
        self.client.force_login(self.user)
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=None,
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
            'period': f'{self.period_1.pk}', 
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
            ''
        )
        self.assertEqual(
            d["ref"],
            payment.ref
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_current_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
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
            'period': f'{self.period_1.pk}', 
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
        )
        self.assertEqual(
            d["current"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_1_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
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
            'period': f'{self.period_2.pk}', 
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
        )
        self.assertEqual(
            d["current"],
            0
        )
        self.assertEqual(
            d["1 month"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_2_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
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
            'period': f'{self.period_3.pk}', 
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )
        self.assertEqual(
            d["3 month"],
            0
        )
        self.assertEqual(
            d["4 month"],
            0
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_3_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
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
            'period': f'{self.period_4.pk}', 
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )
        self.assertEqual(
            d["4 month"],
            0
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_4_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
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
            'period': f'{self.period_5.pk}', 
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=50,
            total=100,
            paid=50,
            status="c"
        )
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="2",
            period=self.period_1,
            date=date.today(),
            due=-50,
            total=-100,
            paid=-50,
            status="c"
        )
        match = PurchaseMatching.objects.create(
            matched_by=invoice,
            matched_to=payment,
            period=self.period_1,
            value=-50,
            matched_by_type="pi",
            matched_to_type="pp"
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
            'period': f'{self.period_1.pk}', 
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
        self.assertEqual(
            data['draw'],
            1
        )
        self.assertEqual(
            data['recordsTotal'],
            2
        )
        self.assertEqual(
            data['recordsFiltered'],
            2
        )
        self.assertEqual(
            len(data['data']),
            2
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
            invoice.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["due_date"],
            invoice.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            d["ref"],
            invoice.ref
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
        )
        self.assertEqual(
            d["current"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )


        d = data["data"][1]
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
            ''
        )
        self.assertEqual(
            d["ref"],
            payment.ref
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_unmatching_where_is_matched_to(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_2,
            date=date.today(),
            due_date=date.today(),
            due=50,
            total=100,
            paid=50,
            status="c"
        )
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="2",
            period=self.period_1,
            date=date.today(),
            due=-50,
            total=-100,
            paid=-50,
            status="c"
        )
        match = PurchaseMatching.objects.create(
            matched_by=invoice,
            matched_to=payment,
            period=self.period_2,
            value=-50,
            matched_by_type="pi",
            matched_to_type="pp"
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
            'period': f'{self.period_1.pk}',
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
            ''
        )
        self.assertEqual(
            d["ref"],
            payment.ref
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            '-100.00'
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_missing_previous_periods(self):
        self.client.force_login(self.user)
        # any old transaction in the period being reported on will do
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=None,
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
            'period': f'{self.period_1.pk}', 
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
            ''
        )
        self.assertEqual(
            d["ref"],
            payment.ref
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )



class AgedCreditorReportWithOutTransactionsTests(TestCase):
    """
    Repeat the above tests but this time check the report without transactions i.e.
    the transactions are grouped by supplier and added up....
    """


    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code='1', name='1')
        cls.url = reverse("purchases:creditors_report")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period_1 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        cls.period_2 = Period.objects.create(
            fy=fy, period="02", fy_and_period="202002", month_start=date(2020, 2, 29))
        cls.period_3 = Period.objects.create(
            fy=fy, period="03", fy_and_period="202003", month_start=date(2020, 3, 31))
        cls.period_4 = Period.objects.create(
            fy=fy, period="04", fy_and_period="202004", month_start=date(2020, 4, 30))
        cls.period_5 = Period.objects.create(
            fy=fy, period="05", fy_and_period="202005", month_start=date(2020, 5, 31))      

    def test_void_is_excluded(self):
        self.client.force_login(self.user)
        voided_payment = PurchaseHeader.objects.create(
                type="pp",
                supplier=self.supplier,
                ref="1",
                period=self.period_1,
                date=date.today(),
                due_date=None,
                due=-100,
                total=-100,
                paid=0,
                status="v"
            )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
        )
        self.assertEqual(
            data['recordsTotal'],
            0
        )
        self.assertEqual(
            data['recordsFiltered'],
            0
        )
        self.assertEqual(
            len(data['data']),
            0
        )

    def test_payment_is_in_unallocated(self):
        self.client.force_login(self.user)
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=None,
            due=-100,
            total=-100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_current_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
        )
        self.assertEqual(
            d["current"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_1_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_2.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
        )
        self.assertEqual(
            d["current"],
            0
        )
        self.assertEqual(
            d["1 month"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_2_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_3.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )
        self.assertEqual(
            d["3 month"],
            0
        )
        self.assertEqual(
            d["4 month"],
            0
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_3_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_4.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )
        self.assertEqual(
            d["4 month"],
            0
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_4_month_old_debt(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_5.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(invoice.total)
        )
        self.assertEqual(
            d["unallocated"],
            0
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
            str(invoice.due)
        )

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_invoice_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=date.today(),
            due=50,
            total=100,
            paid=50,
            status="c"
        )
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="2",
            period=self.period_1,
            date=date.today(),
            due=-50,
            total=-100,
            paid=-50,
            status="c"
        )
        match = PurchaseMatching.objects.create(
            matched_by=invoice,
            matched_to=payment,
            period=self.period_1,
            value=-50,
            matched_by_type="pi",
            matched_to_type="pp"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            '0.00'
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
        )
        self.assertEqual(
            d["current"],
            str(invoice.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_unmatching_where_is_matched_to(self):
        self.client.force_login(self.user)
        invoice = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            period=self.period_2,
            date=date.today(),
            due_date=date.today(),
            due=50,
            total=100,
            paid=50,
            status="c"
        )
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="2",
            period=self.period_1,
            date=date.today(),
            due=-50,
            total=-100,
            paid=-50,
            status="c"
        )
        match = PurchaseMatching.objects.create(
            matched_by=invoice,
            matched_to=payment,
            period=self.period_2,
            value=-50,
            matched_by_type="pi",
            matched_to_type="pp"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            '-100.00'
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )

    def test_missing_previous_periods(self):
        self.client.force_login(self.user)
        # any old transaction in the period being reported on will do
        payment = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            period=self.period_1,
            date=date.today(),
            due_date=None,
            due=-100,
            total=-100,
            paid=0,
            status="c"
        )
        d = {
            'draw': '2', 
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
            'period': f'{self.period_1.pk}', 
            'use_adv_search': 'yes'
        }
        q = dict_to_url(d)
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        data = json.loads(content)
        # report is run for first period
        # check that 1 month debt and older each has zero value
        # in doing so we also check report does not error either
        self.assertEqual(
            data['draw'],
            2
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
            ''
        )
        self.assertEqual(
            d["due_date"],
            ''
        )
        self.assertEqual(
            d["ref"],
            ''
        )
        self.assertEqual(
            d["total"],
            str(payment.total)
        )
        self.assertEqual(
            d["unallocated"],
            str(payment.due)
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

        DT_RowData = d["DT_RowData"]
        self.assertEqual(
            DT_RowData["pk"],
            None
        )
        self.assertEqual(
            DT_RowData["href"],
            None
        )
import json
from datetime import date

from accountancy.testing.helpers import dict_to_url, encodeURI
from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from sales.models import SaleHeader, Customer

DATE_OUTPUT_FORMAT = '%d %b %Y'

class TranEnquiryTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(code='1', name='1')
        cls.url = reverse("sales:transaction_enquiry")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_basic(self):
        p = SaleHeader.objects.create(
            type="si",
            customer=self.customer,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        self.client.force_login(self.user)
        # the url is turned into a dict within the enquiry views
        # here we start with a dict because it is easier to understand
        url_as_dict = {
            'draw': '1', 
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'customer__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'period__fy_and_period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            }, 
            'start': '0', 
            'length': '10', 
            'search': {'value': '', 'regex': 'false'}, 
            'customer': '', 
            'reference': '', 
            'total': '', 
            'period': '', 
            'search_within': 'any', 
            'start_date': '', 
            'end_date': '', 
            'use_adv_search': 'True'
        }
        q = dict_to_url(url_as_dict)
        # would be nice to pass url_as_dict as the data keyword argument to self.client.get
        # but django does not deal with the nested dict the way we want
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        d = json.loads(content)
        self.assertEqual(
            d['draw'],
            1
        )
        self.assertEqual(
            d['recordsTotal'],
            1
        )
        self.assertEqual(
            len(d['data']),
            1
        )
        tran = d['data'][0]
        self.assertEqual(
            tran['id'],
            p.pk
        )
        self.assertEqual(
            tran['customer__name'],
            p.customer.name
        )
        self.assertEqual(
            tran['ref'],
            p.ref
        )
        self.assertEqual(
            tran['period__fy_and_period'],
            p.period.fy_and_period[4:] + " " + p.period.fy_and_period[:4]
        )
        self.assertEqual(
            tran['date'],
            p.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['due_date'],
            p.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['total'],
            str(p.total)
        )
        self.assertEqual(
            tran['paid'],
            str(p.paid)
        )
        self.assertEqual(
            tran['due'],
            str(p.due)
        )
        row_data = tran['DT_RowData']
        self.assertEqual(
            row_data['pk'],
            p.pk
        )
        self.assertEqual(
            row_data['href'],
            f'/sales/view/{p.pk}'
        )
        self.assertIsNotNone(
            d["form"]
        )
        # manually UI test the form
        
    def test_void_not_included(self):
        p = SaleHeader.objects.create(
            type="si",
            customer=self.customer,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="v"
        )
        self.client.force_login(self.user)
        # the url is turned into a dict within the enquiry views
        # here we start with a dict because it is easier to understand
        url_as_dict = {
            'draw': '1', 
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'customer__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'period__fy_and_period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            }, 
            'start': '0', 
            'length': '10', 
            'search': {'value': '', 'regex': 'false'}, 
            'customer': '', 
            'reference': '', 
            'total': '', 
            'period': '', 
            'search_within': 'any', 
            'start_date': '', 
            'end_date': '', 
            'use_adv_search': 'True'
        }
        q = dict_to_url(url_as_dict)
        # would be nice to pass url_as_dict as the data keyword argument to self.client.get
        # but django does not deal with the nested dict the way we want
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        d = json.loads(content)
        self.assertEqual(
            d['draw'],
            1
        )
        self.assertEqual(
            d['recordsTotal'],
            1
        )
        self.assertEqual(
            len(d['data']),
            0
        )
        self.assertIsNotNone(
            d["form"]
        )
        # manually UI test the form

    def test_filter_form(self):
        # filter form test was needed before we changed client so that it always uses the filter form
        # so testing here a user input into the form
        p = SaleHeader.objects.create(
            type="si",
            customer=self.customer,
            ref="1",
            period=self.period,
            date=date.today(),
            due_date=date.today(),
            due=100,
            total=100,
            paid=0,
            status="c"
        )
        self.client.force_login(self.user)
        # the url is turned into a dict within the enquiry views
        # here we start with a dict because it is easier to understand
        url_as_dict = {
            'draw': '1', 
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'customer__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'period__fy_and_period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            }, 
            'start': '0', 
            'length': '10', 
            'search': {'value': '', 'regex': 'false'}, 
            'customer': str(self.customer.pk), 
            'reference': '', 
            'total': '', 
            'period': '', 
            'search_within': 'any', 
            'start_date': '', 
            'end_date': '', 
            'use_adv_search': 'True'
        }
        q = dict_to_url(url_as_dict)
        # would be nice to pass url_as_dict as the data keyword argument to self.client.get
        # but django does not deal with the nested dict the way we want
        response = self.client.get(
            self.url + "?" + q,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        content = response.content.decode("utf")
        d = json.loads(content)
        self.assertEqual(
            d['draw'],
            1
        )
        self.assertEqual(
            d['recordsTotal'],
            1
        )
        self.assertEqual(
            len(d['data']),
            1
        )
        tran = d['data'][0]
        self.assertEqual(
            tran['id'],
            p.pk
        )
        self.assertEqual(
            tran['customer__name'],
            p.customer.name
        )
        self.assertEqual(
            tran['ref'],
            p.ref
        )
        self.assertEqual(
            tran['period__fy_and_period'],
            p.period.fy_and_period[4:] + " " + p.period.fy_and_period[:4]
        )
        self.assertEqual(
            tran['date'],
            p.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['due_date'],
            p.due_date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['total'],
            str(p.total)
        )
        self.assertEqual(
            tran['paid'],
            str(p.paid)
        )
        self.assertEqual(
            tran['due'],
            str(p.due)
        )
        row_data = tran['DT_RowData']
        self.assertEqual(
            row_data['pk'],
            p.pk
        )
        self.assertEqual(
            row_data['href'],
            '/sales/view/' + str(p.pk)
        )
        self.assertIsNotNone(
            d["form"]
        )
        # manually UI test the form
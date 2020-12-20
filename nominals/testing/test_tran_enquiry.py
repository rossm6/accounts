import json
from datetime import date
from decimal import Decimal

from accountancy.testing.helpers import dict_to_url, encodeURI
from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction

DATE_OUTPUT_FORMAT = '%d %b %Y'
TWO_PLACES = Decimal(10) ** -2

class TranEnquiryTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.nominal = Nominal.objects.create(
            name="expenses",
        )
        cls.url = reverse("nominals:transaction_enquiry")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_basic(self):
        t = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=1,
            nominal=self.nominal,
            value=Decimal(100).quantize(TWO_PLACES),
            period=self.period,
            date=date(2020,1,31),
            type="pi",
            ref="123"
        )
        self.client.force_login(self.user)
        # the url is turned into a dict within the enquiry views
        # here we start with a dict because it is easier to understand
        url_as_dict = {
            'draw': '1', 
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'module', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'header', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'nominal__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'period__fy_and_period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            }, 
            'start': '0', 
            'length': '10', 
            'search': {'value': '', 'regex': 'false'}, 
            'nominal': '',
            'reference': '', 
            'total': '', 
            'period': '', 
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
            tran['nominal__name'],
            t.nominal.name
        )
        self.assertEqual(
            tran['ref'],
            t.ref
        )
        self.assertEqual(
            tran['period__fy_and_period'],
            t.period.fy_and_period[4:] + " " + t.period.fy_and_period[:4]
        )
        self.assertEqual(
            tran['date'],
            t.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['total'],
            str(t.value)
        )
        row_data = tran['DT_RowData']
        # client uses the module and the DT_RowData pk which is actually the header attribute
        self.assertEqual(
            row_data['pk'],
            t.header
        )
        self.assertEqual(
            row_data['href'],
            '/purchases/view/1'
        )
        self.assertIsNotNone(
            d["form"]
        )
        # manually UI test the form
        
    def test_filter_form(self):
        t = NominalTransaction.objects.create(
            module="PL",
            header=1,
            line=1,
            nominal=self.nominal,
            value=Decimal(100).quantize(TWO_PLACES),
            period=self.period,
            date=date(2020,1,31),
            type="pi",
            ref="123"
        )
        self.client.force_login(self.user)
        # the url is turned into a dict within the enquiry views
        # here we start with a dict because it is easier to understand
        url_as_dict = {
            'draw': '1', 
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}}, 
                1: {'data': 'module', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                2: {'data': 'header', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                3: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                4: {'data': 'nominal__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                5: {'data': 'period__fy_and_period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                6: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}, 
                7: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            }, 
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            }, 
            'start': '0', 
            'length': '10', 
            'search': {'value': '', 'regex': 'false'}, 
            'nominal': str(self.nominal.pk),
            'reference': '', 
            'total': '', 
            'period': '', 
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
            tran['nominal__name'],
            t.nominal.name
        )
        self.assertEqual(
            tran['ref'],
            t.ref
        )
        self.assertEqual(
            tran['period__fy_and_period'],
            t.period.fy_and_period[4:] + " " + t.period.fy_and_period[:4]
        )
        self.assertEqual(
            tran['date'],
            t.date.strftime(DATE_OUTPUT_FORMAT)
        )
        self.assertEqual(
            tran['total'],
            str(t.value)
        )
        row_data = tran['DT_RowData']
        # client uses the module and the DT_RowData pk which is actually the header attribute
        self.assertEqual(
            row_data['pk'],
            t.header
        )
        self.assertEqual(
            row_data['href'],
            '/purchases/view/1'
        )
        self.assertIsNotNone(
            d["form"]
        )
        # manually UI test the form
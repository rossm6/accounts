from datetime import datetime, timedelta
from json import loads

from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accountancy.testing.helpers import *
from cashbook.models import CashBook, CashBookTransaction
from nominals.models import Nominal, NominalTransaction
from accountancy.helpers import sort_multiple
from vat.models import Vat

from ..helpers import (create_credit_note_with_lines,
                       create_credit_note_with_nom_entries,
                       create_invoice_with_lines,
                       create_invoice_with_nom_entries, create_invoices,
                       create_lines, create_receipt_with_nom_entries,
                       create_receipts, create_refund_with_nom_entries)
from ..models import SaleHeader, SaleLine, SaleMatching, Customer

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
MATCHING_FORM_PREFIX = "match"
PERIOD = '202007'  # the calendar month i made the change !
SL_MODULE = "SL"


class ViewInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime('%Y-%m-%d')

        cls.description = "a line description"

        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.sale_control = Nominal.objects.create(
            parent=current_assets, name="Sales Ledger Control"
        )

        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")

        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)

    def test(self):

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {

                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20,
            self.vat_nominal,
            self.sale_control
        )

        headers = SaleHeader.objects.all()
        header = headers[0]

        response = self.client.get(
            reverse("sales:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            response.context["header_to_edit"],
            header
        )


class ViewBroughtForwardInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime('%Y-%m-%d')

        cls.description = "a line description"

        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)

    def test(self):

        header, lines = create_invoice_with_lines(
            {
                "type": "sbi",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {

                    'description': self.description,
                    'goods': 100,
                    'vat': 20
                }
            ] * 20,
        )

        headers = SaleHeader.objects.all()
        header = headers[0]

        response = self.client.get(
            reverse("sales:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            response.context["header_to_edit"],
            header
        )

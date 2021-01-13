from datetime import date, datetime, timedelta
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.models import CashBook, CashBookTransaction
from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone
from nominals.models import Nominal, NominalTransaction
from sales.helpers import (create_credit_note_with_lines,
                           create_credit_note_with_nom_entries,
                           create_invoice_with_lines,
                           create_invoice_with_nom_entries, create_invoices,
                           create_lines, create_receipt_with_nom_entries,
                           create_receipts, create_refund_with_nom_entries,
                           create_vat_transactions)
from sales.models import Customer, SaleHeader, SaleLine, SaleMatching
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
SL_MODULE = "SL"
DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

def match(match_by, matched_to):
    headers_to_update = []
    matches = []
    match_total = 0
    for match_to, match_value in matched_to:
        match_total += match_value
        match_to.due = match_to.due - match_value
        match_to.paid = match_to.total - match_to.due
        matches.append(
            SaleMatching(
                matched_by=match_by,
                matched_to=match_to,
                value=match_value,
                period=match_by.period
            )
        )
        headers_to_update.append(match_to)
    match_by.due = match_by.total + match_total
    match_by.paid = match_by.total - match_by.due
    SaleHeader.objects.bulk_update(
        headers_to_update + [match_by], ['due', 'paid'])
    SaleMatching.objects.bulk_create(matches)
    return match_by, headers_to_update


def create_cancelling_headers(n, customer, ref_prefix, type, value, period):
    """
    Create n headers which cancel out with total = value
    Where n is an even number
    """
    date = timezone.now()
    due_date = date + timedelta(days=31)
    headers = []
    n = int(n / 2)
    for i in range(n):
        i = SaleHeader(
            customer=customer,
            ref=ref_prefix + str(i),
            goods=value,
            discount=0,
            vat=0,
            total=value,
            paid=0,
            due=value,
            date=date,
            due_date=due_date,
            type=type,
            period=period
        )
        headers.append(i)
    for i in range(n):
        i = SaleHeader(
            customer=customer,
            ref=ref_prefix + str(i),
            goods=value * -1,
            discount=0,
            vat=0,
            total=value * -1,
            paid=0,
            due=value * -1,
            date=date,
            due_date=due_date,
            type=type,
            period=period
        )
        headers.append(i)
    return SaleHeader.objects.bulk_create(headers)


class CreateReceiptNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
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
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("sales:create")
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    # CORRECT USAGE
    # A receipt with no matching
    def test_non_zero_receipt(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_zero_receipt(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.customer, "match", "si", 100, self.period)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("-pk")
        self.assertEqual(len(headers), 3)
        header = headers[0]
        self.assertEqual(
            header.total,
            0
        )
        self.assertEqual(
            header.goods,
            0
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            0
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[2]
        )
        self.assertEqual(
            matches[0].value,
            100
        )
        self.assertEqual(
            matches[1].matched_by,
            header
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[1].value,
            -100
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_negative_receipt(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.goods,
            120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )    
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            -120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

#     """

#     Test matching for positive receipts

#     """

    # CORRECT USAGE
    def test_fully_matched_positive_receipt(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1, self.period, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 120})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            -120
        )
        self.assertEqual(
            receipt.goods,
            -120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            -120
        )
        self.assertEqual(
            receipt.due,
            0
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            120
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = receipt

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_zero_value_match_positive_receipt(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            -120
        )
        self.assertEqual(
            receipt.goods,
            -120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -120
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = receipt

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_match_value_too_high(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, 200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 120.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120.00</li>',
            html=True
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice = headers[0]

        self.assertEqual(
            invoice.total,
            240
        )
        self.assertEqual(
            invoice.goods,
            200
        )
        self.assertEqual(
            invoice.vat,
            40
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            240
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    # INCORRECT USAGE
    def test_match_value_too_low(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, -200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -0.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120.00</li>',
            html=True
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice = headers[0]

        self.assertEqual(
            invoice.total,
            -240
        )
        self.assertEqual(
            invoice.goods,
            -200
        )
        self.assertEqual(
            invoice.vat,
            -40
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            -240
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    # CORRECT USAGE
    def test_match_ok_and_not_full_match(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 60})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            -120
        )
        self.assertEqual(
            receipt.goods,
            -120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            -60
        )
        self.assertEqual(
            receipt.due,
            -60
        )

        self.assertEqual(
            invoice.total,
            120
        )
        self.assertEqual(
            invoice.goods,
            100
        )
        self.assertEqual(
            invoice.vat,
            20
        )
        self.assertEqual(
            invoice.paid,
            60
        )
        self.assertEqual(
            invoice.due,
            60
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            60
        )

        header = receipt

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


#     """
#     Test matching for negative receipts
#     """

    # CORRECT USAGE
    def test_fully_matched_negative_receipt_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -120})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            120
        )
        self.assertEqual(
            receipt.goods,
            120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            120
        )
        self.assertEqual(
            receipt.due,
            0
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            -120
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = receipt

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            -120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

#     # CORRECT USAGE
    def test_zero_value_match_negative_receipt_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            120
        )
        self.assertEqual(
            receipt.goods,
            120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            120
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = receipt

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            -120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

#     # INCORRECT USAGE
    def test_match_value_too_high_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, -200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -120.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120.00</li>',
            html=True
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice = headers[0]

        self.assertEqual(
            invoice.total,
            -240
        )
        self.assertEqual(
            invoice.goods,
            -200
        )
        self.assertEqual(
            invoice.vat,
            -40
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            -240
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_match_value_too_low_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, 200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120.00</li>',
            html=True
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice = headers[0]

        self.assertEqual(
            invoice.total,
            240
        )
        self.assertEqual(
            invoice.goods,
            200
        )
        self.assertEqual(
            invoice.vat,
            40
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            240
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0        
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

#     # CORRECT USAGE
    def test_match_ok_and_not_full_match_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.customer, "inv", 1,self.period, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -60})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(match_form_prefix, matching_forms)

        data.update(header_data)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        receipt = headers[1]
        invoice = headers[0]
        self.assertEqual(
            receipt.total,
            120
        )
        self.assertEqual(
            receipt.goods,
            120
        )
        self.assertEqual(
            receipt.vat,
            0
        )
        self.assertEqual(
            receipt.ref,
            self.ref
        )
        self.assertEqual(
            receipt.paid,
            60
        )
        self.assertEqual(
            receipt.due,
            60
        )

        self.assertEqual(
            invoice.total,
            -120
        )
        self.assertEqual(
            invoice.goods,
            -100
        )
        self.assertEqual(
            invoice.vat,
            -20
        )
        self.assertEqual(
            invoice.paid,
            -60
        )
        self.assertEqual(
            invoice.due,
            -60
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            receipt.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            receipt.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            receipt.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )  

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            -60
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = receipt

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            -120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

# """
# EDIT
# """

class EditReceiptNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
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
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )


    # CORRECT USAGE
    # A non-zero receipt is reduced
    def test_non_zero_receipt(self):
        self.client.force_login(self.user)
        create_receipt_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "sp",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 120,
                "due": 120,
                "paid": 0,
                "period": self.period,
            },
            self.sale_control,
            self.nominal
        )
        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 100
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -100
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            100
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control
        )
        self.assertEqual(
            tran.value,
            -100
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            100
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_non_zero_receipt_is_changed_to_zero(self):
        self.client.force_login(self.user)
        create_receipt_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "sp",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 120,
                "due": 120,
                "paid": 0,
                "period": self.period
            },
            self.sale_control,
            self.nominal
        )

        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.customer, "match", "si", 100, self.period)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 3)
        header = headers[0]
        self.assertEqual(
            header.total,
            0
        )
        self.assertEqual(
            header.goods,
            0
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    # CORRECT USAGE
    def test_zero_receipt_is_changed_to_non_zero(self):
        self.client.force_login(self.user)
        create_receipt_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "sp",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 0,
                "due": 0,
                "paid": 0,
                "period": self.period
            },
            self.sale_control,
            self.nominal
        )

        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            0
        )
        self.assertEqual(
            header.goods,
            0
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_1(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sr",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -0.01
            }
        )
        data.update(header_data)

        matching_forms = []
        matching_forms.append({
            "type": headers[0].type,
            "ref": headers[0].ref,
            "total": headers[0].total * -1,
            "paid": headers[0].paid * -1,
            "due": headers[0].due * -1,
            "matched_by": '',
            "matched_to": headers[0].pk,
            "value": headers[0].total * -1,
        })
        matching_forms.append({
            "type": headers[1].type,
            "ref": headers[1].ref,
            "total": headers[1].total,
            "paid": headers[1].paid,
            "due": headers[1].due,
            "matched_by": '',
            "matched_to": headers[1].pk,
            "value": headers[1].total,
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        self.assertEqual(
            matches[0].matched_by,
            headers[2]
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]
        )
        self.assertEqual(
            matches[0].value,
            two_dp(-120.01)
        )
        self.assertEqual(
            matches[1].matched_by,
            headers[2]
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[1].value,
            120
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)

        matching_forms = []
        matching_forms.append({
            "type": headers[2].type,
            "ref": headers[2].ref,
            "total": headers[2].total * -1,
            "paid": headers[2].paid * -1,
            "due": headers[2].due * -1,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": '-110.01',
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("sales:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            3
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_2(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sr",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -0.01
            }
        )
        data.update(header_data)
        matching_forms = []
        matching_forms.append({
            "type": headers[0].type,
            "ref": headers[0].ref,
            "total": headers[0].total * -1,
            "paid": headers[0].paid * -1,
            "due": headers[0].due * -1,
            "matched_by": '',
            "matched_to": headers[0].pk,
            "value": headers[0].total * -1,
        })
        matching_forms.append({
            "type": headers[1].type,
            "ref": headers[1].ref,
            "total": headers[1].total,
            "paid": headers[1].paid,
            "due": headers[1].due,
            "matched_by": '',
            "matched_to": headers[1].pk,
            "value": headers[1].total,
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(reverse("sales:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        self.assertEqual(
            matches[0].matched_by,
            headers[2]
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]
        )
        self.assertEqual(
            matches[0].value,
            two_dp(-120.01)
        )
        self.assertEqual(
            matches[1].matched_by,
            headers[2]
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[1].value,
            120
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "sp",
                "cash_book": self.cash_book.pk,
                "customer": self.customer.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)

        matching_forms = []
        matching_forms.append({
            "type": headers[2].type,
            "ref": headers[2].ref,
            "total": headers[2].total * -1,
            "paid": headers[2].paid * -1,
            "due": headers[2].due * -1,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": '-120.02',
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("sales:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            3
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    def test_edit_header_only(self):
        # change the period only - header only attribute - and check it feeds through to NL and VL and CB trans
        self.client.force_login(self.user)

        create_receipt_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "sp",
                "customer": self.customer,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 120,
                "due": 120,
                "paid": 0,
                "period": self.period
            },
            self.sale_control,
            self.nominal
        )

        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        self.assertEqual(
            header.period,
            self.period
        )

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            self.period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            cash_book_trans[0].period,
            self.period
        )

        new_period = Period.objects.create(fy=self.fy, fy_and_period="202008", period="08", month_start=date(2020,8,31))

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "sp",
                "customer": self.customer.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120,
                "period": new_period.pk
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = SaleHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.goods,
            -120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            0
        )
        self.assertEqual(
            header.due,
            header.total
        )
        self.assertEqual(
            header.period,
            new_period
        )  
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        self.assertEqual(
            tran.line,
            1
        )
        self.assertEqual(
            tran.nominal,
            self.nominal # bank nominal
        )
        self.assertEqual(
            tran.value,
            120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            new_period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )
        self.assertEqual(
            tran.module,
            SL_MODULE
        )
        self.assertEqual(
            tran.header,
            header.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.sale_control # bank nominal
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            header.ref
        )
        self.assertEqual(
            tran.period,
            new_period
        )     
        self.assertEqual(
            tran.date,
            header.date
        )
        self.assertEqual(
            tran.field,
            't'
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'SL'
        )
        self.assertEqual(
            cash_book_trans[0].header,
            header.pk
        )
        self.assertEqual(
            cash_book_trans[0].line,
            1
        )
        self.assertEqual(
            cash_book_trans[0].cash_book,
            self.cash_book
        )
        self.assertEqual(
            cash_book_trans[0].value,
            120
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )
        self.assertEqual(
            cash_book_trans[0].period,
            new_period
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )
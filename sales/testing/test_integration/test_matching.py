from datetime import date, datetime, timedelta

from accountancy.testing.helpers import *
from cashbook.models import CashBook
from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from django.utils import timezone
from nominals.models import Nominal
from sales.helpers import (create_credit_note_with_lines,
                           create_credit_note_with_nom_entries,
                           create_invoice_with_lines,
                           create_invoice_with_nom_entries, create_invoices,
                           create_lines, create_receipt_with_nom_entries,
                           create_receipts, create_refund_with_nom_entries,
                           create_vat_transactions)
from sales.models import Customer, SaleHeader, SaleLine, SaleMatching
from vat.models import Vat

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
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


class CreateTransactionMatching(TestCase):
    """
    This is more straight forward than edit.

    Whenever a new transaction is created and it is matched to others we only need to -

        1. check that match allocation will leave a valid outstanding on the tran to be matched to
        2. check that the sum of the match values gives a valid outstanding / paid figure for the tran being created
    """

    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.sale_control = Nominal.objects.create(
            parent=current_assets, name="Sales Ledger Control")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("sales:create")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    # VALID USAGE
    # So we match transactions with cancel out
    def test_create_zero_value_1(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(
            2, self.customer, "match", "si", 100, self.period)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [to_dict(header)
                            for header in headers_to_match_against]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {
                                                  "id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        # NO LINES NEED BUT CODE STILL NEEDS THE LINE MANAGEMENT FORM
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        new_header = SaleHeader.objects.filter(ref=self.ref)
        self.assertEqual(len(list(new_header)), 1)
        new_header = new_header[0]
        self.assertEqual(new_header.total, 0)
        self.assertEqual(new_header.paid, 0)
        self.assertEqual(new_header.due, 0)
        map_pk_to_header = {
            header.pk: header for header in headers_to_match_against_orig}
        headers_to_match_against_updated = new_header.matched_to.all()
        # CHECK THE HEADERS WE ELECTED TO MATCH AGAINST HAVE BEEN UPDATED CORRECTLY
        for header in headers_to_match_against_updated:
            # total should not have changed
            self.assertEqual(
                header.total,
                map_pk_to_header[header.pk].total
            )
            self.assertEqual(
                header.due,
                0
            )
            # should be all paid
            self.assertEqual(
                header.paid,
                map_pk_to_header[header.pk].total
            )
        matches = SaleMatching.objects.all()
        self.assertEqual(len(matches), 2)
        for match in matches:
            matched_to_header_before_update = map_pk_to_header[match.matched_to_id]
            self.assertEqual(
                match.matched_by_id,
                new_header.pk
            )
            self.assertEqual(
                match.value,
                matched_to_header_before_update.due
            )
            self.assertEqual(
                match.period,
                self.period
            )

    # VALID USAGE
    def test_create_positive_with_outstanding_2(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2000)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2000})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        invoice = headers[1]
        self.assertEqual(
            invoice.total,
            2400
        )
        self.assertEqual(
            invoice.paid,
            2000
        )
        self.assertEqual(
            invoice.due,
            400
        )
        self.assertEqual(
            receipt.total,
            -2000
        )
        self.assertEqual(
            receipt.paid,
            -2000
        )
        self.assertEqual(
            receipt.due,
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt
        )
        self.assertEqual(
            matches[0].value,
            -2000
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID USAGE
    def test_create_positive_overmatched_3(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please ensure the total of the transactions you are matching is between 0 and 2400"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # VALID USAGE
    def test_create_positive_fully_matched_4(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2400)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        invoice = headers[1]
        self.assertEqual(
            invoice.total,
            2400
        )
        self.assertEqual(
            invoice.paid,
            2400
        )
        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            -2400
        )
        self.assertEqual(
            receipt.due,
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt
        )
        self.assertEqual(
            matches[0].value,
            -2400
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID USAGE
    # E.G. Invoice for 100 is matched to invoice for 10.00
    def test_create_positive_undermatched_5(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please ensure the total of the transactions you are matching is between 0 and 2400"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # VALID USAGE
    def test_create_negative_with_outstanding_6(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2000)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2000})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        invoice = headers[1]
        self.assertEqual(
            invoice.total,
            -2400
        )
        self.assertEqual(
            invoice.paid,
            -2000
        )
        self.assertEqual(
            invoice.due,
            -400
        )
        self.assertEqual(
            receipt.total,
            2000
        )
        self.assertEqual(
            receipt.paid,
            2000
        )
        self.assertEqual(
            receipt.due,
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt
        )
        self.assertEqual(
            matches[0].value,
            2000
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID USAGE
    def test_create_negative_with_overmatched_7(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please ensure the total of the transactions you are matching is between 0 and -2400"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # VALID USAGE
    def test_create_negative_with_fully_matched_8(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2400)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        invoice = headers[1]
        self.assertEqual(
            invoice.total,
            -2400
        )
        self.assertEqual(
            invoice.paid,
            -2400
        )
        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            receipt.total,
            2400
        )
        self.assertEqual(
            receipt.paid,
            2400
        )
        self.assertEqual(
            receipt.due,
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt
        )
        self.assertEqual(
            matches[0].value,
            2400
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID USAGE
    # E.G. Invoice for -100 is matched to invoice for -10.00
    def test_create_negative_undermatched_9(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please ensure the total of the transactions you are matching is between 0 and -2400"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # INVALID USAGE
    # E.G. try and match an invoice of 100 to a credit note of 50, where you allocate 100 on credit note
    def test_match_value_is_invalid_for_matched_to_transaction_by_overallocating_10a_negative_tran(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2600})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 2500"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # this time overallocate a positive tran
    def test_match_value_is_invalid_for_matched_to_transaction_by_overallocating_10b_positive_tran(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2600})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between -2500.00 and 0"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # INVALID USAGE
    # E.G. try and match an invoice of 100 to a credit note of 50, where you allocate -50 on credit note
    def test_match_value_is_invalid_for_matched_to_transaction_by_underallocating_11a_negative_tran(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 2500"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    def test_match_value_is_invalid_for_matched_to_transaction_by_underallocating_11b_positive_tran(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -2500)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2500})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between -2500.00 and 0"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            2500
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            2500
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # INVALID USAGE
    # Fully matched transactions will not show in the UI to match to transactions being created
    # But we can't rely on this obviously.
    def test_match_value_is_invalid_for_matched_to_transaction_when_matched_to_is_already_fully_matched_12(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2400)[0]
        receipt.due = 0
        receipt.paid = -2400
        receipt.save()
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This transaction is not outstanding."
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            -2400
        )
        self.assertEqual(
            receipt.due,
            0
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # INVALID USAGE
    def test_match_value_is_invalid_for_matched_to_transaction_when_matched_to_is_already_partially_matched_13(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2400)[0]
        receipt.due = -100
        receipt.paid = -2300
        receipt.save()
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 100"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            -2300
        )
        self.assertEqual(
            receipt.due,
            -100
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    def test_cannot_match_a_transaction_with_status_void_37(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, 2400)[0]
        receipt.status = "v"
        receipt.save()
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot match to a void transaction"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2400
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    def test_cannot_match_to_a_transaction_on_another_account_39(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        other_customer = Customer.objects.create(code="other", name="other")
        receipt = create_receipts(
            other_customer, "receipt", 1, self.period, 2400)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot match to a transaction which belongs to another account"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2400
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    def test_cannot_match_to_a_transaction_in_a_later_period_40(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "si",
                "customer": self.customer.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'nominal': self.nominal.pk,
            'vat_code': self.vat_code.pk,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        # invoice is for 2400
        next_period = Period.objects.create(
            fy=self.fy, period="02", fy_and_period="202002", month_start=date(2020, 2, 29))
        receipt = create_receipts(
            self.customer, "receipt", 1, next_period, 2400)[0]
        headers_as_dicts = [to_dict(receipt)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot match to a transaction which is in a later period"
        )
        headers = SaleHeader.objects.all().order_by("pk")
        receipt = headers[0]
        self.assertEqual(
            receipt.total,
            -2400
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -2400
        )

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )


class EditTransactionMatching(TestCase):
    """
    Editing transactions is tricker than creating transactions when it comes to the matching.
    """

    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.sale_control = Nominal.objects.create(
            parent=current_assets, name="Sales Ledger Control")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("sales:create")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    """
    Most obvious considerations first - just change existing match values
    """

    # VALID
    # CHANGE VALUES FOR EXISTING MATCHES
    def test_change_a_match_value_so_matched_by_is_now_outstanding_14(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -1200)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            invoice.paid,
            2400
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            -1200
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matching_forms[-1]["value"] = 600
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # VALID
    # CHANGE VALUES FOR EXISTING MATCHES
    def test_change_a_match_value_so_matched_by_is_now_fully_matched_15(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matching_forms[-1]["value"] = 1200
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            invoice.paid,
            2400
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            -1200
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # VALID
    # CHANGE VALUES FOR EXISTING MATCHES SO EACH IS ZERO
    def test_change_a_match_value_so_matched_by_is_now_fully_outstanding_16(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 0})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            -1200
        )
        self.assertEqual(
            receipt1.paid,
            0
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -1200
        )
        self.assertEqual(
            receipt2.paid,
            0
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            0
        )

    """
    Now change values for single match and check matched_to

    Some of this will be implicitly tested in the above already.
    """

    # VALID
    def test_increasing_a_match_value_so_matched_to_is_now_fully_paid_17(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            invoice.paid,
            2400
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            -1200
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID

    def test_increasing_a_match_value_so_matched_to_is_overallocated_18(self):

        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["value"] = 1500
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 1200.00"
        )

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # VALID
    # I.E. set value to 0 so that match is removed
    # I.E. DELETE MATCH
    def test_decreasing_a_match_value_so_matched_to_is_now_fully_outstanding_19(self):

        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 0
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1200
        )
        self.assertEqual(
            invoice.paid,
            1200
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -1200
        )
        self.assertEqual(
            receipt2.paid,
            0
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID
    def test_decreasing_a_match_value_so_matched_to_is_now_underallocated_20(self):

        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = -1200
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 1200"
        )

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    """
    Same tests again but this time matched_to is matched to something else too.
    """

    # VALID
    def test_increasing_a_match_value_so_matched_to_is_now_fully_paid_21(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.paid = -400
        receipt2.due = -800
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -200
        )
        self.assertEqual(
            receipt2.paid,
            -1000
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 800
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            400
        )
        self.assertEqual(
            invoice.paid,
            2000
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            -1200
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -800
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    def test_increasing_a_match_value_so_matched_to_is_overallocated_22(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.paid = -400
        receipt2.due = -800
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -200
        )
        self.assertEqual(
            receipt2.paid,
            -1000
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 800.01
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 800"
        )

    # VALID
    def test_decreasing_a_match_value_so_matched_to_is_matched_only_to_other_tran_23(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.paid = -400
        receipt2.due = -800
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -200
        )
        self.assertEqual(
            receipt2.paid,
            -1000
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 0
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1200
        )
        self.assertEqual(
            invoice.paid,
            1200
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -800
        )
        self.assertEqual(
            receipt2.paid,
            -400
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

    # INVALID
    # I.E. doing this would lower match value of match between matched_to and the other tran
    def test_decreasing_a_match_value_so_matched_to_is_now_underallocated_24(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.paid = -400
        receipt2.due = -800
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -200
        )
        self.assertEqual(
            receipt2.paid,
            -1000
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = -10
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Value must be between 0 and 800"
        )

    """
    Now change the outstanding of the transaction being edited by ADDING a new match
    """

    # VALID
    def test_adding_match_to_increase_outstanding_25(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])
        receipt3 = create_receipts(
            self.customer, "receipt", 1, self.period, -1200)[0]

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            1200
        )
        self.assertEqual(
            receipt3.paid,
            0
        )
        self.assertEqual(
            receipt3.total,
            1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2, receipt3]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_forms[2]["value"] = -600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        receipt3.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1200
        )
        self.assertEqual(
            invoice.paid,
            1200
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            600
        )
        self.assertEqual(
            receipt3.paid,
            600
        )
        self.assertEqual(
            receipt3.total,
            1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            3
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )
        self.assertEqual(
            matches[2].matched_by,
            invoice
        )
        self.assertEqual(
            matches[2].matched_to,
            receipt3
        )
        self.assertEqual(
            matches[2].value,
            600
        )
        self.assertEqual(
            matches[2].period,
            self.period
        )

    # VALID
    def test_adding_match_to_make_tran_fully_outstanding_26(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])
        receipt3 = create_receipts(
            self.customer, "receipt", 1, self.period, -1800)[0]

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            1800
        )
        self.assertEqual(
            receipt3.paid,
            0
        )
        self.assertEqual(
            receipt3.total,
            1800
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2, receipt3]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_forms[2]["value"] = -1800
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        receipt3.refresh_from_db()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            0
        )
        self.assertEqual(
            receipt3.paid,
            1800
        )
        self.assertEqual(
            receipt3.total,
            1800
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            3
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )
        self.assertEqual(
            matches[2].matched_by,
            invoice
        )
        self.assertEqual(
            matches[2].matched_to,
            receipt3
        )
        self.assertEqual(
            matches[2].value,
            1800
        )
        self.assertEqual(
            matches[2].period,
            self.period
        )

    # VALID
    def test_adding_match_to_decrease_outstanding_27(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])
        receipt3 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            -1200
        )
        self.assertEqual(
            receipt3.paid,
            0
        )
        self.assertEqual(
            receipt3.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2, receipt3]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_forms[2]["value"] = 500
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        receipt3.refresh_from_db()

        self.assertEqual(
            invoice.due,
            100
        )
        self.assertEqual(
            invoice.paid,
            2300
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            -700
        )
        self.assertEqual(
            receipt3.paid,
            -500
        )
        self.assertEqual(
            receipt3.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            3
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )
        self.assertEqual(
            matches[2].matched_by,
            invoice
        )
        self.assertEqual(
            matches[2].matched_to,
            receipt3
        )
        self.assertEqual(
            matches[2].value,
            -500
        )
        self.assertEqual(
            matches[2].period,
            self.period
        )

    # VALID
    def test_adding_match_to_make_tran_fully_matched_28(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        receipt2.save()
        match(invoice, [(receipt1, -1200), (receipt2, -600)])
        receipt3 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            -1200
        )
        self.assertEqual(
            receipt3.paid,
            0
        )
        self.assertEqual(
            receipt3.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1, receipt2, receipt3]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_forms[2]["value"] = 600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        receipt3.refresh_from_db()

        self.assertEqual(
            invoice.due,
            0
        )
        self.assertEqual(
            invoice.paid,
            2400
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        self.assertEqual(
            receipt3.due,
            -600
        )
        self.assertEqual(
            receipt3.paid,
            -600
        )
        self.assertEqual(
            receipt3.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            3
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )
        self.assertEqual(
            matches[2].matched_by,
            invoice
        )
        self.assertEqual(
            matches[2].matched_to,
            receipt3
        )
        self.assertEqual(
            matches[2].value,
            -600
        )
        self.assertEqual(
            matches[2].period,
            self.period
        )

    """
    All tests above involve editing the match values where the transaction being edited is the
    matched_by in the match relationship.

    Now we need to check editing when the transaction being edited is the matched_to in the relationship.
    """

    # VALID
    # I.E. outstanding of tran which is matched_by in match relationship is valid
    def test_increase_match_value_legal_29(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 1200)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -600
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": 800})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            400
        )
        self.assertEqual(
            invoice.paid,
            2000
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            -400
        )
        self.assertEqual(
            receipt2.paid,
            -800
        )
        self.assertEqual(
            receipt2.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -800
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    # I.E. outstanding of tran which is matched_by in match relationship is invalid
    def test_increase_match_value_illegal_30(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1, receipt2 = create_receipts(
            self.customer, "receipt", 2, self.period, 2000)
        match(invoice, [(receipt1, -1200), (receipt2, -600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            -800
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -2000
        )

        self.assertEqual(
            receipt2.due,
            -1400
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -2000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": 1800})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Not allowed because it would mean a due of -600.00 for this transaction when the total is 2400.00"
        )

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            600
        )
        self.assertEqual(
            invoice.paid,
            1800
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            -800
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -2000
        )

        self.assertEqual(
            receipt2.due,
            -1400
        )
        self.assertEqual(
            receipt2.paid,
            -600
        )
        self.assertEqual(
            receipt2.total,
            -2000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            -600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # VALID
    # I.E. outstanding of tran which is matched_by in match relationship is valid
    # We should try and create another test where we edit receipt1 instead

    def test_decrease_match_value_legal_31(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            3800
        )
        self.assertEqual(
            receipt2.paid,
            1200
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    # I.E. outstanding of tran which is matched_by in match relationship is invalid
    def test_decrease_match_value_illegal_32(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        # 2400 invoice matched to a 1200 receipt gives 1200 outstanding
        # match a receipt for -3600 gives outstanding of 4800.  Nonsense !

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -3600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Not allowed because it would mean a due of 4800.00 for this transaction when the total is 2400.00"
        )

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    # This time the match value means the due would be between 0 and the current due and the initial
    # value but it does NOT respect the total
    # This one is for a positive total (but shows in UI as negative)
    def test_decrease_match_value_illegal_32a_positive(self):

        self.client.force_login(self.user)
        receipt = create_receipts(
            self.customer, "receipt", 1, self.period, -1.00)[0]
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1201)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -1200)[0]
        match(receipt, [(receipt1, -1201), (receipt2, 1200)])

        receipt.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            receipt.due,
            0
        )
        self.assertEqual(
            receipt.paid,
            1.00
        )
        self.assertEqual(
            receipt.total,
            1.00
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1201
        )
        self.assertEqual(
            receipt1.total,
            -1201
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            1200
        )
        self.assertEqual(
            receipt2.total,
            1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1201
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            receipt
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        url = reverse("sales:edit", kwargs={"pk": receipt1.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt1.type,
                "customer": receipt1.customer.pk,
                "period": receipt1.period.pk,
                "ref": receipt1.ref,
                "date": receipt1.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt1.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [receipt]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -1199.99})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[0]["matched_to"] = receipt1.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Not allowed because it would mean a due of -1.01 for this transaction when the total is -1.00"
        )

        receipt.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            receipt.due,
            0
        )
        self.assertEqual(
            receipt.paid,
            1.00
        )
        self.assertEqual(
            receipt.total,
            1.00
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1201
        )
        self.assertEqual(
            receipt1.total,
            -1201
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            1200
        )
        self.assertEqual(
            receipt2.total,
            1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1201.00
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            receipt
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            1200.00
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    def test_decrease_match_value_illegal_32a_negative(self):
        pass

    """
    Add new match transaction.  Tran being edited is still the matched_to in at least one of the matches
    """

    # VALID
    def test_add_tran_so_nothing_outstanding_on_tran_being_edited_legal_33(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        # create new invoice to match
        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": -4400,
                "paid": 0,
                "due": -4400,
                "goods": -4000,
                "vat": -400
            },
            [
                {
                    'description': self.description,
                    'goods': -400,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': -40
                }
            ] * 10,
            self.vat_nominal,
            self.sale_control
        )

        new_invoice = SaleHeader.objects.filter(type="si").last()

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice, new_invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_forms[1]["matched_by"] = receipt2.pk
        matching_forms[1]["matched_to"] = new_invoice.pk
        matching_forms[1]["value"] = -4400
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        new_invoice.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            0
        )
        self.assertEqual(
            receipt2.paid,
            5000
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        self.assertEqual(
            new_invoice.due,
            0
        )
        self.assertEqual(
            new_invoice.paid,
            -4400
        )
        self.assertEqual(
            new_invoice.total,
            -4400
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            3
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        self.assertEqual(
            matches[2].matched_by,
            receipt2
        )
        self.assertEqual(
            matches[2].matched_to,
            new_invoice
        )
        self.assertEqual(
            matches[2].value,
            -4400
        )
        self.assertEqual(
            matches[2].period,
            self.period
        )

    """
    Need two tests.  One which hits both branches of the code.
    """

    # INVALID
    # Adding the new match would mean an invalid paid / outstanding for the tran being edited
    # E.G.
    # Payment is created for 1000 and matched to three invoices for 500 and a credit note for 500
    # Now try and edit one of the 500 invoices by adding a new match to 100 invoice.
    # The 100 match value for the invoice is valid.
    # And a 100 match value for this invoice means a -100 match value for the tran being edited
    # -100 + 500 = 400 which is a valid paid figure implying a new outstanding figure of 100
    # Obviously this is nonsense though because the invoice for 500 is fully matched to the receipt for 1000.
    # So the outstanding cannot be changed to 100.
    def test_add_tran_illegal_34(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        receipt3 = create_receipts(
            self.customer, "receipt", 1, self.period, -600)[0]

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": receipt2.customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice, receipt3]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_forms[1]["matched_by"] = receipt2.pk
        matching_forms[1]["matched_to"] = receipt3.pk
        matching_forms[1]["value"] = -600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        receipt3.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        self.assertEqual(
            receipt3.due,
            600
        )
        self.assertEqual(
            receipt3.paid,
            0
        )
        self.assertEqual(
            receipt3.total,
            600
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    # NOT POSSIBLE THROUGH UI BUT STILL NEEDS TESTING

    def test_cannot_match_transaction_to_itself_35(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": invoice.period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "due_date": invoice.due_date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": 600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["matched_to"] = invoice.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cannot match a transaction to itself.")
        invoice.refresh_from_db()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            0
        )

    def test_cannot_match_a_transaction_with_status_void_36(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400,
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]

        invoice.refresh_from_db()
        receipt1.refresh_from_db()

        self.assertEqual(
            invoice.due,
            2400
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        # here we match with models only so matching is possible

        self.assertEqual(
            receipt1.due,
            -1200
        )
        self.assertEqual(
            receipt1.paid,
            0
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        invoice.status = "v"
        invoice.save()

        url = reverse("sales:edit", kwargs={"pk": receipt1.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt1.type,
                "customer": receipt1.customer.pk,
                "period": receipt1.period.pk,
                "ref": receipt1.ref,
                "date": receipt1.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt1.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 600})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot match to a void transaction"
        )

    def test_cannot_change_customer_if_there_are_matches_38(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400,
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        # here we match with models only so matching is possible

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)

        new_customer = Customer.objects.create(name="new", code="new")

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": new_customer.pk,
                "period": receipt2.period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You cannot change the customer if the transaction is matched to other transactions. Please remove the matches first."
        )

    def test_cannot_change_period_so_matched_by_period_is_less_than_matched_to_41(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400
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

        invoice = SaleHeader.objects.first()

        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        match(invoice, [(receipt1, -1200)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1200
        )
        self.assertEqual(
            invoice.paid,
            1200
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

        # later period
        last_fy = FinancialYear.objects.create(financial_year=2019, number_of_periods=1)
        last_period = Period.objects.create(
            fy=last_fy, period="01", fy_and_period="201901", month_start=date(2019, 1, 31))
        url = reverse("sales:edit", kwargs={"pk": invoice.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": invoice.type,
                "customer": invoice.customer.pk,
                "period": last_period.pk,
                "ref": invoice.ref,
                "date": invoice.date.strftime(DATE_INPUT_FORMAT),
                "total": invoice.total
            }
        )
        data.update(header_data)
        lines = SaleLine.objects.all().order_by("pk")
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)
        matching_trans = [receipt1]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_to"}, {"value": 1200})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[0].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot do this.  In the matched relationship already established the transaction you are editing is B.  The transaction you have "
            "matched B to is this matched transaction A.  The period of A cannot be after the period of B."
        )

        invoice.refresh_from_db()
        receipt1.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1200
        )
        self.assertEqual(
            invoice.paid,
            1200
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )


    def test_cannot_change_period_so_matched_to_period_is_greater_than_matched_by_42(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400,
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

        invoice = SaleHeader.objects.first()
        receipt1 = create_receipts(
            self.customer, "receipt", 1, self.period, 1200)[0]
        receipt2 = create_receipts(
            self.customer, "receipt", 1, self.period, -5000)[0]
        match(invoice, [(receipt1, -1200), (receipt2, 600)])

        invoice.refresh_from_db()
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        self.assertEqual(
            invoice.due,
            1800
        )
        self.assertEqual(
            invoice.paid,
            600
        )
        self.assertEqual(
            invoice.total,
            2400
        )

        # here we match with models only so matching is possible

        self.assertEqual(
            receipt1.due,
            0
        )
        self.assertEqual(
            receipt1.paid,
            -1200
        )
        self.assertEqual(
            receipt1.total,
            -1200
        )

        self.assertEqual(
            receipt2.due,
            4400
        )
        self.assertEqual(
            receipt2.paid,
            600
        )
        self.assertEqual(
            receipt2.total,
            5000
        )

        matches = SaleMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            receipt1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            invoice
        )
        self.assertEqual(
            matches[1].matched_to,
            receipt2
        )
        self.assertEqual(
            matches[1].value,
            600
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        cashbook = CashBook.objects.create(
            name="current", nominal=self.nominal)
        # later period
        next_period = Period.objects.create(
            fy=self.fy, period="02", fy_and_period="202002", month_start=date(2020, 2, 29))

        url = reverse("sales:edit", kwargs={"pk": receipt2.pk})
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": cashbook.pk,
                "type": receipt2.type,
                "customer": self.customer.pk,
                "period": next_period.pk,
                "ref": receipt2.ref,
                "date": receipt2.date.strftime(DATE_INPUT_FORMAT),
                "total": receipt2.total * -1
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        matching_trans = [invoice]
        matching_trans_as_dicts = [to_dict(m) for m in matching_trans]
        matching_trans = [get_fields(
            m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects(
            matching_trans, {"id": "matched_by"}, {"value": -600})
        matches = SaleMatching.objects.all().order_by("pk")
        matching_forms[0]["id"] = matches[1].pk
        matching_forms[0]["matched_to"] = receipt2.pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Cannot do this.  In the matched relationship already established the transaction you are editing is A.  The transaction you "
            "have matched A to is this matched transaction B.  The period of A cannot be after the period of B."
        )

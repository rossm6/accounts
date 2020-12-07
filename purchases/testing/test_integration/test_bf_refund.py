from datetime import date, datetime, timedelta
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.models import CashBook, CashBookTransaction
from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone
from nominals.models import Nominal, NominalTransaction
from purchases.helpers import (create_credit_note_with_lines,
                               create_credit_note_with_nom_entries,
                               create_invoice_with_lines,
                               create_invoice_with_nom_entries,
                               create_invoices, create_lines,
                               create_payment_with_nom_entries,
                               create_payments, create_refund_with_nom_entries)
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
PERIOD = '202007' # the calendar month i made the change !
PL_MODULE = "PL"
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
            PurchaseMatching(
                matched_by=match_by, 
                matched_to=match_to, 
                value=match_value,
                period=match_by.period
            )
        )
        headers_to_update.append(match_to)
    match_by.due = match_by.total + match_total
    match_by.paid = match_by.total - match_by.due
    PurchaseHeader.objects.bulk_update(headers_to_update + [ match_by ], ['due', 'paid'])
    PurchaseMatching.objects.bulk_create(matches)
    return match_by, headers_to_update

def create_cancelling_headers(n, supplier, ref_prefix, type, value, period):
    """
    Create n headers which cancel out with total = value
    Where n is an even number
    """
    date = timezone.now()
    due_date = date + timedelta(days=31)
    headers = []
    n = int(n /2)
    for i in range(n):
        i = PurchaseHeader(
            supplier=supplier,
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
        i = PurchaseHeader(
            supplier=supplier,
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
    return PurchaseHeader.objects.bulk_create(headers)


class CreateBroughtForwardRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create payment view only with t=bp GET parameter
    def test_get_request_with_query_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url + "?t=pbr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr" selected>Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class CreateBroughtForwardRefundNominalEntries(TestCase):

    """
    There shouldn't be any nominal entries.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.url = reverse("purchases:create")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))


    # CORRECT USAGE
    # A payment with no matching
    def test_non_zero_payment(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            120
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
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
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_zero_payment(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100, self.period)
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 3)
        header = headers[2]
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
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
            headers[0]
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
    def test_negative_payment(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
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
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -120
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
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
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    """

    Test matching for positive payments

    """

    # CORRECT USAGE
    def test_fully_matched_positive_payment(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]
        self.assertEqual(
            payment.total,
            120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            120
        )
        self.assertEqual(
            payment.due,
            0
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
            -120
        )
        self.assertEqual(
            invoice.due,
            0
        )

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            payment
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
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_zero_value_match_positive_payment(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]

        self.assertEqual(
            payment.total,
            120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            120
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
            0
        )
        self.assertEqual(
            invoice.due,
            -120
        )

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
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
    def test_match_value_too_high(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -200)[0]
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120.00</li>',
            html=True
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
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

        matches = PurchaseMatching.objects.all()
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
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, 200)[0]
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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

        matches = PurchaseMatching.objects.all()
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
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]
        self.assertEqual(
            payment.total,
            120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            60
        )
        self.assertEqual(
            payment.due,
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

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
 
        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            payment
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
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    """
    Test matching for negative payments
    """

    # CORRECT USAGE
    def test_fully_matched_negative_payment_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, 100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]

        self.assertEqual(
            payment.total,
            -120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            -120
        )
        self.assertEqual(
            payment.due,
            0
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
            120
        )
        self.assertEqual(
            invoice.due,
            0
        )

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            payment
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
            0
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_zero_value_match_negative_payment_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, 100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]
        self.assertEqual(
            payment.total,
            -120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            -120
        )

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
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
    def test_match_value_too_high_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, 200)[0]
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120.00</li>',
            html=True
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
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

        matches = PurchaseMatching.objects.all()
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
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -200)[0]
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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

        matches = PurchaseMatching.objects.all()
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
    def test_match_ok_and_not_full_match_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, 100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]
        self.assertEqual(
            payment.total,
            -120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            -60
        )
        self.assertEqual(
            payment.due,
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

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            60
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

class EditBroughtForwardRefundNominalEntries(TestCase):

    """
    Tests same as EditRefundNominalEntries.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.url = reverse("purchases:create")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))

    # CORRECT USAGE
    # A non-zero payment is reduced
    def test_non_zero_payment(self):
        self.client.force_login(self.user)
        PurchaseHeader.objects.create(**{
            "type": "pbr",
            "supplier": self.supplier,
            "period": self.period,
            "ref": self.ref,
            "date": self.model_date,
            "due_date": self.model_due_date,
            "total": 120,
            "due": 120,
            "paid": 0,
            "goods": 0,
            "vat": 0,          
        })

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            120
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
 
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            100
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
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
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_non_zero_payment_is_changed_to_zero(self):
        self.client.force_login(self.user)
        PurchaseHeader.objects.create(**{
            "type": "pbr",
            "supplier": self.supplier,
            "period": self.period,
            "ref": self.ref,
            "date": self.model_date,
            "due_date": self.model_due_date,
            "total": 120,
            "due": 120,
            "paid": 0,
            "goods": 0,
            "vat": 0,          
        })

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            120
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100, self.period)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all().order_by("pk")
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
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
    def test_zero_payment_is_changed_to_non_zero(self):
        self.client.force_login(self.user)
        PurchaseHeader.objects.create(**{
            "type": "pbr",
            "supplier": self.supplier,
            "period": self.period,
            "ref": self.ref,
            "date": self.model_date,
            "due_date": self.model_due_date,
            "total": 0,
            "due": 0,
            "paid": 0,
            "goods": 0,
            "vat": 0,
        })

        headers = PurchaseHeader.objects.all()
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            120
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )
        matches = PurchaseMatching.objects.all()
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
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_1(self):
        self.client.force_login(self.user)

        # Create a payment for 120.01
        # Create a refund for 120.00
        # Create a payment for -0.01

        # edit the refund with a match value which isn't allowed because not enough outstanding
        # on the payment for -0.01

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbp",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
            "total": headers[0].total,
            "paid": headers[0].paid,
            "due": headers[0].due,
            "matched_by": '',
            "matched_to": headers[0].pk,
            "value": headers[0].total,
        })
        matching_forms.append({
            "type": headers[1].type,
            "ref": headers[1].ref,
            "total": headers[1].total * -1,
            "paid": headers[1].paid * -1,
            "due": headers[1].due * -1,
            "matched_by": '',
            "matched_to": headers[1].pk,
            "value": headers[1].total * -1,
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = PurchaseMatching.objects.all()
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
            two_dp(120.01)
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
            -120
        )

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
            "total": headers[2].total,
            "paid": headers[2].paid,
            "due": headers[2].due,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": '-110.01',
            "id": matches[1].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_2(self):
        self.client.force_login(self.user)
        # Create a payment for 120.01
        # Create a refund for 120.00
        # Create a payment for -0.01

        # edit the first payment with a match value which isn't allowed because not enough outstanding
        # on the payment for -0.01

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbp",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
            "total": headers[0].total,
            "paid": headers[0].paid,
            "due": headers[0].due,
            "matched_by": '',
            "matched_to": headers[0].pk,
            "value": headers[0].total,
        })
        matching_forms.append({
            "type": headers[1].type,
            "ref": headers[1].ref,
            "total": headers[1].total * -1,
            "paid": headers[1].paid * -1,
            "due": headers[1].due * -1,
            "matched_by": '',
            "matched_to": headers[1].pk,
            "value": headers[1].total * -1,
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = PurchaseMatching.objects.all()
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
            two_dp(120.01)
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
            -120
        )

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
            "total": headers[2].total,
            "paid": headers[2].paid,
            "due": headers[2].due,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": '-120.02',
            "id": matches[1].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

class EditBroughtForwardRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))

    # CORRECT USAGE
    def test_get_request(self):
        self.client.force_login(self.user)
        transaction = PurchaseHeader.objects.create(
            type="pbr",
            supplier=self.supplier,
            period=self.period,
            ref="ref",
            date=self.model_date,
            due_date=self.model_due_date,
            total=120,
            goods=100,
            vat=20
        )
        url = reverse("purchases:edit", kwargs={"pk": transaction.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" disabled required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr" selected>Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class MatchingTests(TestCase):
    """

    We need to check -

        1. Transactions created write the transaction header period to the match records (which will all be new)
        2. Transactions which have the period edited changed the period for the match records WHERE THE TRANSACTION BEING EDITED IS THE MATCHED_BY ONLY !!!
    
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.url = reverse("purchases:create")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))


    def test_create(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, self.period, -100)[0]
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
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[1]
        invoice = headers[0]
        self.assertEqual(
            payment.total,
            120
        )
        self.assertEqual(
            payment.goods,
            0
        )
        self.assertEqual(
            payment.vat,
            0
        )
        self.assertEqual(
            payment.ref,
            self.ref
        )
        self.assertEqual(
            payment.paid,
            120
        )
        self.assertEqual(
            payment.due,
            0
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
            -120
        )
        self.assertEqual(
            invoice.due,
            0
        )

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            -120
        )
        self.assertEqual(
            matches[0].period,
            self.period
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


    def test_edit_period_does_not_change_matches(self):
        new_period = Period.objects.create(
            fy=self.fy, fy_and_period="202002", period="02", month_end=date(2020,2,29)
        )
        self.client.force_login(self.user)

        # Create a payment for 120.01
        # Create a refund for 120.00
        # Create a payment for -0.01

        # edit the refund with a match value which isn't allowed because not enough outstanding
        # on the payment for -0.01

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbp",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
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
            "total": headers[0].total,
            "paid": headers[0].paid,
            "due": headers[0].due,
            "matched_by": '',
            "matched_to": headers[0].pk,
            "value": headers[0].total,
        })
        matching_forms.append({
            "type": headers[1].type,
            "ref": headers[1].ref,
            "total": headers[1].total * -1,
            "paid": headers[1].paid * -1,
            "due": headers[1].due * -1,
            "matched_by": '',
            "matched_to": headers[1].pk,
            "value": headers[1].total * -1,
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(matching_data)
        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = PurchaseMatching.objects.all()
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
            two_dp(120.01)
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
            -120
        )

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbr",
                "supplier": self.supplier.pk,
				"period": new_period.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)

        print(matches[0].__dict__)

        matching_forms = []
        matching_forms.append({
            "type": headers[2].type,
            "ref": headers[2].ref,
            "total": headers[2].total,
            "paid": headers[2].paid,
            "due": headers[2].due,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": headers[0].total,
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        
        self.assertEqual(
            response.status_code,
            302
        )

        matches = PurchaseMatching.objects.all()
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
            two_dp(120.01)
        )
        self.assertEqual(
            matches[0].period,
            self.period
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
            -120
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    def test_edit_period_does_change(self):
        pass
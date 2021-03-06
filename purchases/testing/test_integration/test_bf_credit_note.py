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
    PurchaseHeader.objects.bulk_update(
        headers_to_update + [match_by], ['due', 'paid'])
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
    n = int(n / 2)
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


class CreateBroughtForwardCreditNote(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))

    # CORRECT USAGE
    # Can request create brought forward invoice view with t=bi GET parameter
    def test_get_request_with_query_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url + "?t=pbc")
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="pbi">Brought Forward Invoice</option>'
            '<option value="pbc" selected>Brought Forward Credit Note</option>'
            '<option value="pbp">Brought Forward Payment</option>'
            '<option value="pbr">Brought Forward Refund</option>'
            '<option value="pp">Payment</option>'
            '<option value="pr">Refund</option>'
            '<option value="pi">Invoice</option>'
            '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class CreateBroughtForwardCreditNoteNominalTransactions(TestCase):

    """
    A brought forward transaction differs to a non brought forward
    transaction only in that the transaction does not update the nominal accounts.
    """

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31)
        )
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )
        cls.description = "brought forward"
        cls.url = reverse("purchases:create")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")

    # CORRECT USAGE
    # Lines can be entered for brought forward transactions
    # But no nominal or vat_code can be selected

    def test_no_nominals_created(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        self.client.force_login(self.user)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.type,
            'pbc'
        )
        self.assertEqual(
            header.total,
            -20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            -20 * 100
        )
        self.assertEqual(
            header.vat,
            -20 * 20
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(len(nom_trans), 0)
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )

            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.nominal,
                None
            )
            self.assertEqual(
                line.vat_code,
                None
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # Zero value credit note
    # No lines allowed
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_no_lines(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100, self.period)
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
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
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

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        # assuming the lines are created in the same order
        # as the nominal entries....
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
            headers[1]
        )
        self.assertEqual(
            matches[0].value,
            100
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[2]
        )
        self.assertEqual(
            matches[1].value,
            -100
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # Line cannot be zero value
    def test_zero_invoice_with_zero_value_line(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100, self.period)
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
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 0,
            'vat': 0
        }])
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Goods and Vat cannot both be zero.</li>',
            html=True
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    """
    Test matching positive invoices now
    """

    # CORRECT USAGE
    def test_fully_matching_an_invoice(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (-100 + -20)
        )
        self.assertEqual(
            header.goods,
            20 * -100
        )
        self.assertEqual(
            header.vat,
            20 * -20
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            -2400
        )
        self.assertEqual(
            header.due,
            0
        )

        self.assertEqual(
            payment.total,
            2400
        )
        self.assertEqual(
            payment.paid,
            2400
        )
        self.assertEqual(
            payment.due,
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]  # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            2400
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (-100 + -20)
        )
        self.assertEqual(
            header.goods,
            20 * -100
        )
        self.assertEqual(
            header.vat,
            20 * -20
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
            -2400
        )

        self.assertEqual(
            payment.total,
            2400
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # For an credit of 2400 the match value must be between 0 and 2400
    def test_match_total_less_than_zero(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(
            self.supplier, "invoice to match", 1, self.period, -2000)[0]
        headers_as_dicts = [to_dict(invoice_to_match)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -0.01})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice_to_match = headers[0]
        self.assertEqual(
            invoice_to_match.total,
            -2400
        )
        self.assertEqual(
            invoice_to_match.paid,
            0
        )
        self.assertEqual(
            invoice_to_match.due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # Try and match 2400.01 to a credit for 2400
    def test_match_total_greater_than_invoice_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "invoice to match", 1, self.period, -2500)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400.01})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        payment = headers[0]
        self.assertEqual(
            payment.total,
            2500
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            2500
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # We've already tested we can match the whole amount and matching 0 does not count
    # Now try matching for value in between
    def test_matching_a_value_but_not_whole_amount(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -1200})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            -20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            -20 * 100
        )
        self.assertEqual(
            header.vat,
            -20 * 20
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            -1200
        )
        self.assertEqual(
            header.due,
            -1200
        )

        self.assertEqual(
            payment.total,
            2400
        )
        self.assertEqual(
            payment.paid,
            1200
        )
        self.assertEqual(
            payment.due,
            1200
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]  # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            1200
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    """
    Test negative credits now.  I've not repeated all the tests
    that were done for positives.  We shouldn't need to.
    """

    # CORRECT USAGE
    def test_negative_credit_entered_without_matching_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 20
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_negative_credit_without_matching_with_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -2400
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 20
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    """
    Test matching negative credits now
    """

    # CORRECT USAGE
    def test_fully_matching_a_negative_credit_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 20
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            2400
        )
        self.assertEqual(
            header.due,
            0
        )

        self.assertEqual(
            payment.total,
            -2400
        )
        self.assertEqual(
            payment.paid,
            -2400
        )
        self.assertEqual(
            payment.due,
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]  # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            -2400
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value_against_negative_invoice_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 20
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
            2400
        )

        self.assertEqual(
            payment.total,
            -2400
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # For a credit of -2400 the match value must be between 0 and 2400

    def test_match_total_greater_than_zero_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(
            self.supplier, "invoice to match", 1, self.period, 2000)[0]
        headers_as_dicts = [to_dict(invoice_to_match)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0.01})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        invoice_to_match = headers[0]
        self.assertEqual(
            invoice_to_match.total,
            2400
        )
        self.assertEqual(
            invoice_to_match.paid,
            0
        )
        self.assertEqual(
            invoice_to_match.due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # Try and match 2400.01 to a credit for -2400
    def test_match_total_less_than_invoice_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "invoice to match", 1, self.period, 2500)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400.01})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
            html=True
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 1)
        payment = headers[0]
        self.assertEqual(
            payment.total,
            -2500
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            -2500
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # We've already tested we can match the whole amount and matching 0 does not count
    # Now try matching for value in between

    def test_matching_a_value_but_not_whole_amount_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 1200})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': -100,
            'vat': -20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 20
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            1200
        )
        self.assertEqual(
            header.due,
            1200
        )

        self.assertEqual(
            payment.total,
            -2400
        )
        self.assertEqual(
            payment.paid,
            -1200
        )
        self.assertEqual(
            payment.due,
            -1200
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]  # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


class EditBroughtForwardCreditNote(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    # CORRECT USAGE

    def test_get_request(self):
        self.client.force_login(self.user)
        transaction = PurchaseHeader.objects.create(
            type="pbc",
            supplier=self.supplier,
            ref="ref",
            date=self.model_date,
            due_date=self.model_date,
            total=120,
            goods=100,
            vat=20,
            period=self.period
        )
        url = reverse("purchases:edit", kwargs={"pk": transaction.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" disabled required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="pbi">Brought Forward Invoice</option>'
            '<option value="pbc" selected>Brought Forward Credit Note</option>'
            '<option value="pbp">Brought Forward Payment</option>'
            '<option value="pbr">Brought Forward Refund</option>'
            '<option value="pp">Payment</option>'
            '<option value="pr">Refund</option>'
            '<option value="pi">Invoice</option>'
            '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class EditBroughtForwardCreditNoteNominalEntries(TestCase):

    """
    Based on same tests as EditCreditNoteNominalTransactions 
    except of course we always expect no nominal output
    """

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        cls.description = "a line description"
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )


    # CORRECT USAGE
    # Basic edit here in so far as we just change a line value

    def test_no_nominals_created_for_lines_with_goods_and_vat_above_zero(self):
        self.client.force_login(self.user)
        # function will still work for credit notes
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we half the goods and vat for a line
                "total": (-1 * header.total) - 60
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_forms[-1]["goods"] = -50
        line_forms[-1]["vat"] = -10
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2340
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2340
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.line_no, i + 1)
        self.assertEqual(edited_line.header, header)

        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, -50)
        self.assertEqual(edited_line.nominal, None)
        self.assertEqual(edited_line.vat_code, None)
        self.assertEqual(edited_line.vat, -10)
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            None
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # Add another line this time
    def test_no_nominals_created_for_new_line(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we half the goods and vat for a line
                "total": (-1 * header.total) + 120
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        last_line_form = line_forms[-1].copy()
        last_line_form["id"] = ""
        line_forms.append(last_line_form)
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2520
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2520
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            21
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        # NOW CHECK THE EDITED

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # Based on above
    # Except this time we reduce goods to zero on a line
    # This should delete the corresponding nominal transaction for goods
    # And obviously change the control account nominal value
    def test_goods_reduced_to_zero_but_vat_non_zero_on_a_line(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we set goods = 0 when previously was 100
                "total": (-1 * header.total) - 100
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = -20
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2300
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2300
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # 19 goods nominal transactions
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.line_no, i + 1)

        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, 0)
        self.assertEqual(edited_line.nominal, None)
        self.assertEqual(edited_line.vat_code, None)
        self.assertEqual(edited_line.vat, -20)
        # NOMINAL TRANSACTION FOR GOODS IS REMOVED
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            None
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # Same as above except we now blank out vat and not goods
    def test_vat_reduced_to_zero_but_goods_non_zero_on_a_line(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we set vat = 0 when previously was 20
                "total": (-1 * header.total) - 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_forms[-1]["goods"] = -100
        line_forms[-1]["vat"] = -0
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2380
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2380
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.line_no, i + 1)

        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, -100)
        self.assertEqual(edited_line.nominal, None)
        self.assertEqual(edited_line.vat_code, None)
        self.assertEqual(edited_line.vat, 0)
        # NOMINAL TRANSACTION FOR GOODS IS REMOVED
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            None
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # Zero out the goods and the vat
    # We expect the line and the three nominal transactions to all be deleted
    def test_goods_and_vat_for_line_reduced_to_zero(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we set vat = 0 when previously was 20
                "total": (-1 * header.total) - 120
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 0
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Goods and Vat cannot both be zero.</li>',
            html=True
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # SIMPLY MARK A LINE AS DELETED
    def test_line_marked_as_deleted_has_line_and_nominals_removed(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[(lambda h: h.pk, False)])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                # we set vat = 0 when previously was 20
                "total": (-1 * header.total) - 120
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id',  'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        line_forms[-1]["goods"] = -100
        line_forms[-1]["vat"] = -20
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_forms[-1]["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2280
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2280
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            19
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    # DELETE ALL THE LINES SO IT IS A ZERO INVOICE
    def test_non_zero_brought_forward_credit_is_changed_to_zero_invoice_by_deleting_all_lines(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all()

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                "total": 0
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id', 'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        for form in line_forms:
            form["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        # WE HAVE TO MATCH OTHERWISE IT WILL ERROR
        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100, self.period)
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
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 3)

        self.assertEqual(
            headers[0].total,
            0
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
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
            headers[0]
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[0].value,
            100
        )
        self.assertEqual(
            matches[1].matched_by,
            headers[0]
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[2]
        )
        self.assertEqual(
            matches[1].value,
            -100
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # CORRECT USAGE
    def test_change_zero_brought_forward_invoice_to_a_non_zero_invoice(self):
        self.client.force_login(self.user)
        header = PurchaseHeader.objects.create(
            **{
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "paid": 0,
                "due": 0
            }
        )

        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100, self.period)
        match(header, [(headers_to_match_against[0], 100),
                       (headers_to_match_against[1], -100)])

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )
        self.assertEqual(
            headers[0].total,
            0
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        self.assertEqual(
            matches[0].matched_by,
            headers[0]
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[0].value,
            100
        )
        self.assertEqual(
            matches[1].matched_by,
            headers[0]
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[2]
        )
        self.assertEqual(
            matches[1].value,
            -100
        )

        header = headers[0]

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                "total": 2400
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100,
                'vat': 20
            }
        ] * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

        # WE HAVE TO MATCH OTHERWISE IT WILL ERROR
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
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)
        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )
        self.assertEqual(
            headers[1].total,
            100
        )
        self.assertEqual(
            headers[1].paid,
            100
        )
        self.assertEqual(
            headers[1].due,
            0
        )
        self.assertEqual(
            headers[2].total,
            -100
        )
        self.assertEqual(
            headers[2].paid,
            -100
        )
        self.assertEqual(
            headers[2].due,
            0
        )

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)

            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            2
        )
        self.assertEqual(
            matches[0].matched_by,
            headers[0]
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[1]
        )
        self.assertEqual(
            matches[0].value,
            100
        )
        self.assertEqual(
            matches[1].matched_by,
            headers[0]
        )
        self.assertEqual(
            matches[1].matched_to,
            headers[2]
        )
        self.assertEqual(
            matches[1].value,
            -100
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_1(self):
        self.client.force_login(self.user)
        # Create a credit for 120.01 through view first
        # Second create a invoice note for 120.00
        # Third create an invoice for 0.01 and match the other two to it
        # Invalid edit follows

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        response = self.client.post(reverse("purchases:create"), data)
        self.assertEqual(
            response.status_code,
            302
        )

        # Credit Note for 120.00
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbi",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.00
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.00,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -0.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': -0.01,
                'vat': 0
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Credit for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_forms[0]["id"] = lines[0].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)

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

        response = self.client.post(
            reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
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
        # Create a credit for 120.01 through view first
        # Second create a invoice note for 120.00
        # Third create an invoice for 0.01 and match the other two to it
        # Invalid edit follows

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbi",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.00
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.00,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -0.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': -0.01,
                'vat': 0
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Credit for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_forms[0]["id"] = lines[0].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)

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

        response = self.client.post(
            reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    # Add another line this time but mark it as deleted
    def test_new_line_marked_as_deleted_does_not_count(self):
        self.client.force_login(self.user)
        header, lines = create_credit_note_with_lines(
            {
                "type": "pbc",
                "supplier": self.supplier,
                "period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
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

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "supplier": header.supplier.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                "total": header.total * -1
            }
        )
        data.update(header_data)
        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(
            line, ['id', 'description', 'goods', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        last_line_form = line_forms[-1].copy()
        last_line_form["id"] = ""
        last_line_form["DELETE"] = "YEP"
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_forms.append(last_line_form)
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)

        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            -2400
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
        lines = list(lines)

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, -20)
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        # NOW CHECK THE EDITED

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


class MatchingTests(TestCase):
    """
    We need to check -

        1. Transactions created write the transaction header period to the match records (which will all be new)
        2. Transactions which have the period edited changed the period for the match records WHERE THE TRANSACTION BEING EDITED IS THE MATCHED_BY ONLY !!!
    """

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31)
        )
        cls.description = "brought forward"
        cls.url = reverse("purchases:create")
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )


    def test_create(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "payment", 1, self.period, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400})
        matching_data = create_formset_data(
            match_form_prefix, matching_forms)
        line_forms = ([{
            'description': self.description,
            'goods': 100,
            'vat': 20
        }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(len(headers), 2)
        payment = headers[0]
        header = headers[1]

        self.assertEqual(
            header.total,
            20 * (-100 + -20)
        )
        self.assertEqual(
            header.goods,
            20 * -100
        )
        self.assertEqual(
            header.vat,
            20 * -20
        )
        self.assertEqual(
            header.ref,
            self.ref
        )
        self.assertEqual(
            header.paid,
            -2400
        )
        self.assertEqual(
            header.due,
            0
        )

        self.assertEqual(
            payment.total,
            2400
        )
        self.assertEqual(
            payment.paid,
            2400
        )
        self.assertEqual(
            payment.due,
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        for i, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                i + 1
            )
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )
        self.assertEqual(
            matches[0].matched_by,
            header
        )
        self.assertEqual(
            matches[0].matched_to,
            headers[0]  # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            2400
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    def test_edit_does_not_change_period(self):
        """
        Test here that the period on the match record is not changed because we are editing the matched_to in the match relationship

        After validating that the matched_to period cannot be after the period of the matched by i changed the test so the match is
        done in 02 2020.  The matched_to is then edited so that the period is 02 2020.
        """
        self.client.force_login(self.user)
        # Create a credit for 120.01 through view first
        # Second create a invoice note for 120.00
        # Third create an invoice for 0.01 and match the other two to it
        # Invalid edit follows

        new_period = Period.objects.create(
            fy=self.fy, fy_and_period="202002", period="02", month_start=date(2020, 2, 29))

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": new_period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbi",
                "supplier": self.supplier.pk,
                "period": new_period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.00
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.00,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": new_period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -0.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': -0.01,
                'vat': 0
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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
            matches[0].period,
            new_period
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
        self.assertEqual(
            matches[1].period,
            new_period
        )

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_forms[0]["id"] = lines[0].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)

        matching_forms = []
        matching_forms.append({
            "type": headers[2].type,
            "ref": headers[2].ref,
            "total": headers[2].total * -1,
            "paid": headers[2].paid * -1,
            "due": headers[2].due * -1,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": headers[0].total,
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(
            reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        matches = PurchaseMatching.objects.all().order_by("pk")
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
            matches[0].period,
            new_period
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
        self.assertEqual(
            matches[1].period,
            new_period
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    def test_edit_does_change_period(self):
        self.client.force_login(self.user)
        # Create a credit for 120.01 through view first
        # Second create a invoice note for 120.00
        # Third create an invoice for 0.01 and match the other two to it
        # Invalid edit follows

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.01,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbi",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120.00
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': 100.00,
                'vat': 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
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
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -0.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': -0.01,
                'vat': 0
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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
            matches[0].period,
            self.period
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
        self.assertEqual(
            matches[1].period,
            self.period
        )

        # Now for the edit.  In the UI the match value shows as -120.01.  In the DB it shows as 120.01
        # We want to change the value to 110.01.  This isn't ok because the -0.01 invoice can only be
        # matched for 0 and full value.  The edit will mean the matched will be outside this.

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        lines = PurchaseLine.objects.filter(header=headers[2]).all()
        self.assertEqual(
            len(lines),
            1
        )

        new_period = Period.objects.create(
            fy=self.fy, fy_and_period="202002", period="02", month_start=date(2020, 2, 29))

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "period": new_period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -0.01
            }
        )
        data.update(header_data)
        line_forms = [
            {
                'description': self.description,
                'goods': -0.01,
                'vat': 0
            }
        ]
        line_forms[0]["id"] = lines[0].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)

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
            "id": matches[0].pk
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
            "id": matches[1].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)
        response = self.client.post(
            reverse("purchases:edit", kwargs={"pk": headers[2].pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            3
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
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
            matches[0].period,
            new_period
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
        self.assertEqual(
            matches[1].period,
            new_period
        )

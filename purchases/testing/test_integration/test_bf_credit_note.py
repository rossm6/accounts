from datetime import datetime, timedelta
from json import loads

from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.models import CashBook, CashBookTransaction
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
from vat.models import Vat

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
MATCHING_FORM_PREFIX = "match"
PERIOD = '202007'  # the calendar month i made the change !
PL_MODULE = "PL"


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
                period=PERIOD
            )
        )
        headers_to_update.append(match_to)
    match_by.due = match_by.total + match_total
    match_by.paid = match_by.total - match_by.due
    PurchaseHeader.objects.bulk_update(
        headers_to_update + [match_by], ['due', 'paid'])
    PurchaseMatching.objects.bulk_create(matches)
    return match_by, headers_to_update


def create_cancelling_headers(n, supplier, ref_prefix, type, value):
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
            period=PERIOD
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
            period=PERIOD
        )
        headers.append(i)
    return PurchaseHeader.objects.bulk_create(headers)


class CreateBroughtForwardCreditNote(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create brought forward invoice view with t=bi GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pbc")
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
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
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime('%Y-%m-%d')
        cls.description = "brought forward"
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Lines can be entered for brought forward transactions
    # But no nominal or vat_code can be selected

    def test_no_nominals_created(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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

    # CORRECT USAGE
    # Zero value credit note
    # No lines allowed
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_no_lines(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100)
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
            MATCHING_FORM_PREFIX, matching_forms)
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

    # INCORRECT USAGE
    # Line cannot be zero value
    def test_zero_invoice_with_zero_value_line(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(
            2, self.supplier, "match", "pi", 100)
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
            MATCHING_FORM_PREFIX, matching_forms)
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

    """
    Test matching positive invoices now
    """

    # CORRECT USAGE
    def test_fully_matching_an_invoice(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

    # INCORRECT USAGE
    # For an credit of 2400 the match value must be between 0 and 2400
    def test_match_total_less_than_zero(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(
            self.supplier, "invoice to match", 1, -2000)[0]
        headers_as_dicts = [to_dict(invoice_to_match)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -0.01})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
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

    # INCORRECT USAGE
    # Try and match 2400.01 to a credit for 2400

    def test_match_total_greater_than_invoice_total(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "invoice to match", 1, -2500)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -2400.01})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
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

    # CORRECT USAGE
    # We've already tested we can match the whole amount and matching 0 does not count
    # Now try matching for value in between
    def test_matching_a_value_but_not_whole_amount(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": -1200})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

    """
    Test negative credits now.  I've not repeated all the tests
    that were done for positives.  We shouldn't need to.
    """

    # CORRECT USAGE
    def test_negative_credit_entered_without_matching_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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

    # CORRECT USAGE
    def test_negative_credit_without_matching_with_total(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -2400
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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

    """
    Test matching negative credits now
    """

    # CORRECT USAGE
    def test_fully_matching_a_negative_credit_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value_against_negative_invoice_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

    # INCORRECT USAGE
    # For a credit of -2400 the match value must be between 0 and 2400

    def test_match_total_greater_than_zero_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(
            self.supplier, "invoice to match", 1, 2000)[0]
        headers_as_dicts = [to_dict(invoice_to_match)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 0.01})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
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

    # INCORRECT USAGE
    # Try and match 2400.01 to a credit for -2400
    def test_match_total_less_than_invoice_total_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(
            self.supplier, "invoice to match", 1, 2500)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 2400.01})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
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

    # CORRECT USAGE
    # We've already tested we can match the whole amount and matching 0 does not count
    # Now try matching for value in between

    def test_matching_a_value_but_not_whole_amount_NEGATIVE(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pbc",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [to_dict(payment)]
        headers_to_match_against = [get_fields(
            header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {
                                                  "id": "matched_to"}, {"value": 1200})
        matching_data = create_formset_data(
            MATCHING_FORM_PREFIX, matching_forms)
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

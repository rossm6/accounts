from datetime import datetime, timedelta
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.models import CashBook, CashBookTransaction
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
                               create_payments, create_refund_with_nom_entries,
                               create_vat_transactions)
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
PERIOD = '202007' # the calendar month i made the change !
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
    PurchaseHeader.objects.bulk_update(headers_to_update + [ match_by ], ['due', 'paid'])
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


class CreateInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
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

    """

    An invoice like a credit note will normally have positive values entered in the input fields.

    This is the difference -

        Invoice

            Enter positive -> Positive values saved in DB
            Enter negative -> Negative values saved in DB

        Credit Note

            Enter positive -> Negative values saved in DB
            Enter negative -> Positive values saved in DB

    """

    # CORRECT USAGE ... well, acceptable usage rather
    def test_match_with_zero_value_is_ignored(self):
        self.client.force_login(self.user)
        # should the user choose a transaction to match to but enter a 0 value
        # the match record should not be created
        # likewise with edit, any match record changed so that value = 0
        # should entail removing the matching record
        # this second requirements is tested in EditInvoice

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "pi",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        matching_forms[4]["value"] = 0 # last of the positives
        matching_forms[-1]["value"] = 0 # last of the negatives
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, []) # NO LINES NEED BUT CODE STILL NEEDS THE LINE MANAGEMENT FORM
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        new_header = PurchaseHeader.objects.filter(ref=self.ref)
        self.assertEqual(len(list(new_header)), 1)
        new_header = new_header[0]
        self.assertEqual(new_header.total, 0)
        self.assertEqual(new_header.paid, 0)
        self.assertEqual(new_header.due, 0)
        map_pk_to_header = { header.pk : header for header in headers_to_match_against_orig }
        headers_to_match_against_updated  = new_header.matched_to.all()
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
        # THE MATCHING TABLE IS THE MEANS THROUGH WHICH THIS MANYTOMANY RELATIONSHIP BETWEEN HEADERS IS ESTABLISHED
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 8)
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
                match.matched_to_id,
                matched_to_header_before_update.pk
            )
        # check now that the headers which had match values of 0 are ok
        unaffected_headers = PurchaseHeader.objects.filter(
            pk__in=[
                matching_forms[4]["matched_to"],
                matching_forms[-1]["matched_to"]
            ]
        ).order_by("pk")

        self.assertEqual(
            len(unaffected_headers),
            2
        )
        self.assertEqual(
            unaffected_headers[0].due,
            100
        )
        self.assertEqual(
            unaffected_headers[0].paid,
            0
        )
        self.assertEqual(
            unaffected_headers[1].due,
            -100
        )
        self.assertEqual(
            unaffected_headers[1].paid,
            0
        )
    
        vat_trans = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_trans),
            0
        )



    # CORRECT USAGE
    # Can request create invoice view without GET parameters
    def test_get_request(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    # CORRECT USAGE
    # Can request create invoice view with t=i GET parameter
    def test_get_request_with_query_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url + "?t=pi")
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi" selected>Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


    # CORRECT USAGE
    # Test the line no is correct
    def test_line_no(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_no = 0
        for line_form in line_forms:
            line_form["ORDER"] = line_no
            line_no = line_no + 1
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
        lines = PurchaseLine.objects.select_related("vat_code").all().order_by("pk")
        self.assertEqual(len(lines), 20)

        vat_trans = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_trans),
            20
        )

        line_no = 1
        for i, line in enumerate(lines):
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.line_no,
                line_no
            )
            self.assertEqual(
                line.vat_transaction,
                vat_trans[i]
            )
            line_no = line_no + 1

        for i, vat_tran in enumerate(vat_trans):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    # CORRECT USAGE
    def test_entering_blank_lines(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 10
        line_forms += ([{
                'description': '',
                'goods': '',
                'nominal': '',
                'vat_code': '',
                'vat': ''
            }]) * 10
        # NOTE THIS WILL NOT WORK IF WE ORDER OR DELETE ON EMPTY LINES
        # SO ON THE CLIENT WE MUST NOT SET EITHER IF ALL THE FIELDS ARE BLANK
        line_no = 1
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
            10 * (100 + 20)
        )
        self.assertEqual(
            header.goods,
            10 * 100
        )
        self.assertEqual(
            header.vat,
            10 * 20
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
        lines = PurchaseLine.objects.select_related("vat_code").all().order_by("pk")
        self.assertEqual(len(lines), 10)
        vat_trans = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_trans),
            10
        )
        line_no = 1
        for i, line in enumerate(lines):
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.line_no,
                line_no
            )
            line_no = line_no + 1
            self.assertEqual(
                line.vat_transaction,
                vat_trans[i]
            )

        for i, vat_tran in enumerate(vat_trans):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )    


    # INCORRECT USAGE
    def test_invoice_header_is_invalid(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": '999999999999', # non existent primary key for supplier to make form invalid
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 0)
        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )
        
    # INCORRECT USAGE
    def test_invoice_header_is_invalid_with_lines_and_matching(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": '999999999999', # non existent primary key for supplier to make form invalid
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 10
        line_forms += ([{
                'description': '',
                'goods': '',
                'nominal': '',
                'vat_code': '',
                'vat': ''
            }]) * 10
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 10) # 11 if successful
        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )


    # CORRECT USAGE
    def test_invoice_with_positive_input_is_saved_as_positive(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:
            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )

    # CORRECT USAGE
    def test_invoice_with_negative_input_is_saved_as_negative(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 * ( -100 + -20)
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
            header.total
        )
        lines = PurchaseLine.objects.all()
        for line in lines:

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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )


    """

    This section tests putting on a zero value transaction which can only be put on to match
    other transactions.

    """


    # CORRECT USAGE
    # THIS IS A ZERO VALUE HEADER TRANSACTION
    # WHICH IS THE WAY TO MATCH OTHER TRANSACTIONS
    # E.G. AN INVOICE AND CREDIT NOTE ON THE SUPPLIER ACCOUNT NEED MATCHING
    def test_header_total_is_zero_with_no_lines_and_matching_transactions_equal_zero(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "pi",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, []) # NO LINES NEED BUT CODE STILL NEEDS THE LINE MANAGEMENT FORM
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        new_header = PurchaseHeader.objects.filter(ref=self.ref)
        self.assertEqual(len(list(new_header)), 1)
        new_header = new_header[0]
        self.assertEqual(new_header.total, 0)
        self.assertEqual(new_header.paid, 0)
        self.assertEqual(new_header.due, 0)
        map_pk_to_header = { header.pk : header for header in headers_to_match_against_orig }
        headers_to_match_against_updated  = new_header.matched_to.all()
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
        # THE MATCHING TABLE IS THE MEANS THROUGH WHICH THIS MANYTOMANY RELATIONSHIP BETWEEN HEADERS IS ESTABLISHED
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 10)
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


    # INCORRECT USAGE
    def test_header_total_is_zero_with_no_lines_and_matching_transactions_do_not_equal_zero(self):
        self.client.force_login(self.user)
        
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "pi",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        # SO FAR SAME AS TEST ABOVE.  NOW FOR THE DIFFERENCE.
        matching_forms[-1]["value"] = -80
        # Now the values to match do not equal 0 which is not acceptable
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, []) # NO LINES NEED BUT CODE STILL NEEDS THE LINE MANAGEMENT FORM
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        new_header = PurchaseHeader.objects.filter(ref=self.ref)
        self.assertEqual(len(list(new_header)), 0)
        map_pk_to_header = { header.pk : header for header in headers_to_match_against_orig }
        header_tried_to_match_to = PurchaseHeader.objects.filter(pk__in=[ pk for pk in map_pk_to_header ])
        # CHECK NOTHING HAS CHANGED ON THE HEADERS
        for header in header_tried_to_match_to:
            self.assertEqual(
                header.due,
                map_pk_to_header[header.pk].due
            )
            self.assertEqual(
                header.paid,
                map_pk_to_header[header.pk].paid
            )
        self.assertEqual(
            len(
                list(PurchaseMatching.objects.all())
            ),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">You are trying to match a total value of 20.00.'
            '  Because you are entering a zero value transaction the total amount to match must be zero also.</li>',
            html=True
        )


    # INCORRECT USUAGE
    def test_header_total_is_zero_with_no_lines_with_no_matching_transactions(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "pi",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)
        self.assertContains(
            response,
			'<li class="py-1">You are trying to enter a zero value transaction without matching to anything.'
            "  This isn't allowed because it is pointless.</li>",
            html=True
        )


    """
    The following assume the user inputs positive numbers - Usual
    """

    # CORRECT USAGE -- BUT THIS MEANS THE TOTAL OF THE LINES IS USED FOR THE HEADER
    # SO THIS IS NOT A ZERO VALUE MATCHING TRANSACTION
    def test_header_total_is_zero_with_lines_and_no_matching_transactions_selected(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:

            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )


    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_less_than_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 10, -100) # Invoices of -1000 are on the account therefore to match against
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 11)
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
            1000
        )
        self.assertEqual(
            header.due,
            header.total - 1000
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        for line in lines:

            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
        matched_headers = header.matched_to.all()
        for _header in matched_headers: # _header to avoid overwriting header above
            self.assertEqual(
                _header.paid,
                -100
            )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 10)
        seen = {}
        for match in matches:
            if match.matched_to_id in seen:
                self.fail("Matching record with same matched_to found")
            seen[match.matched_to_id] = True # any value will do
            self.assertEqual(
                match.matched_by,
                header
            )
            self.assertEqual(
                match.value,
                -100
            )

    
    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_equal_to_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 24, -100) # Invoices of -1000 are on the account therefore to match against
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 25)
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])
        header = headers[24]
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        for line in lines:

            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
        matched_headers = header.matched_to.all()
        for _header in matched_headers: # _header to avoid overwriting header above
            self.assertEqual(
                _header.paid,
                -100
            )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 24)
        seen = {}
        for match in matches:
            if match.matched_to_id in seen:
                self.fail("Matching record with same matched_to found")
            seen[match.matched_to_id] = True # any value will do
            self.assertEqual(
                match.matched_by,
                header
            )
            self.assertEqual(
                match.value,
                -100
            )


    # INCORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_above_the_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 25, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            25 # the 25 trans created in set up; so not including the one we tried to just create
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400.00</li>',
            html=True
        )

    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1 # the 1 trans created in set up; so not including the one we tried to just create
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
            html=True
        )

    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:

            self.assertEqual(
                line.description,
                self.description
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )

    # INCORRECT USAGE
    def test_header_total_is_non_zero_and_with_lines_which_do_not_total_entered_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2300 # THIS IS DIFFERENT TO 2400, ACTUAL TOTAL OF INVOICE LINES
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 0)
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">The total of the lines does not equal the total you entered.</li>',
            html=True
        )

    """
    These are the same kind of tests but this time we test the user entering negative figures - UNUSUAL but acceptable because a
    negative invoice is just a credit note.

    Use same test names as above except for appending the name with _NEGATIVE

    """

    # CORRECT USAGE -- BUT THIS MEANS THE TOTAL OF THE LINES IS USED FOR THE HEADER
    # SO THIS IS NOT A ZERO VALUE MATCHING TRANSACTION
    def test_header_total_is_zero_with_lines_and_no_matching_transactions_selected_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 * ( -100 + -20)
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
            header.total
        )
        lines = PurchaseLine.objects.all()
        for line in lines:

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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )

    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_less_than_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 10, 100) # Invoices of 1000 are on the account therefore to match against
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 11)
        header = headers[0]
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
            -1000
        )
        self.assertEqual(
            header.due,
            header.total - -1000
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        for line in lines:

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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
        matched_headers = header.matched_to.all()
        for _header in matched_headers: # _header to avoid overwriting header above
            self.assertEqual(
                _header.paid,
                100
            )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 10)
        seen = {}
        for match in matches:
            if match.matched_to_id in seen:
                self.fail("Matching record with same matched_to found")
            seen[match.matched_to_id] = True # any value will do
            self.assertEqual(
                match.matched_by,
                header
            )
            self.assertEqual(
                match.value,
                100
            )

    
    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_equal_to_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 24, 100) # Invoices of -1000 are on the account therefore to match against
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 25)
        header = headers[0]
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        for line in lines:

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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
        matched_headers = header.matched_to.all()
        for _header in matched_headers: # _header to avoid overwriting header above
            self.assertEqual(
                _header.paid,
                100
            )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 24)
        seen = {}
        for match in matches:
            if match.matched_to_id in seen:
                self.fail("Matching record with same matched_to found")
            seen[match.matched_to_id] = True # any value will do
            self.assertEqual(
                match.matched_by,
                header
            )
            self.assertEqual(
                match.value,
                100
            )

    # INCORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_above_the_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 25, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            25 # the 25 trans created in set up; so not including the one we tried to just create
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
            html=True
        )


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1 # the 1 trans created in set up; so not including the one we tried to just create
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
            html=True
        )




    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            header.total
        )
        lines = PurchaseLine.objects.all()
        for line in lines:

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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )

    # INCORRECT USAGE
    def test_header_total_is_non_zero_and_with_lines_which_do_not_total_entered_total_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -2300 # THIS IS DIFFERENT TO 2400, ACTUAL TOTAL OF INVOICE LINES
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 0)
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">The total of the lines does not equal the total you entered.</li>',
            html=True
        )


    """
    So far we have only tested that the total amount of the matching value is ok from the point of view
    of the new header we are creating.  The next four tests check that we cannot match more than is due
    ON THE TRANSACTION WE WANT TO MATCH.


        For a transaction with positive DUE amount we need to check we cannot match where value -

            1. value < 0

            2. or value > due

        
        For a transaction with negative DUE amount we need to check we cannot match where value -

            3. value > 0

            4. or value < due
            
    """

    def test_illegal_matching_situation_1(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -10})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Value must be between 0 and 120.00</li>',
            html=True
        )


    def test_illegal_matching_situation_2(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 130}) # rememeber the invoice we create above is not including VAT. So 120 total, not 100.00
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Value must be between 0 and 120.00</li>',
            html=True
        )

    def test_illegal_matching_situation_3(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, -100) # So -120.00 is the due
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 10})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Value must be between 0 and -120.00</li>',
            html=True
        )

    def test_illegal_matching_situation_4(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, -100) # So -120.00 is the due
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -130}) # Trying to match -130.00 when due is only -120.00
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            1
        )
        self.assertEqual(
            len(PurchaseLine.objects.all()),
            0
        )
        self.assertEqual(
            len(PurchaseMatching.objects.all()),
            0
        )
        self.assertContains(
            response,
			'<li class="py-1">Value must be between 0 and -120.00</li>',
            html=True
        )


class CreateInvoiceNominalEntries(TestCase):

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

    # CORRECT USAGE
    # Each line has a goods value above zero and the vat is 20% of the goods
    def test_nominals_created_for_lines_with_goods_and_vat_above_zero(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.select_related("vat_code").all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (100 + 20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )


    # CORRECT USAGE
    # Each line has a goods value above zero
    # And the vat is a zero value
    # We are only testing here that no nominal transactions for zero are created
    # We are not concerned about the vat return at all
    def test_nominals_created_for_lines_with_goods_above_zero_and_vat_equal_to_zero(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 0
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
            20 * (100 + 0)
        )
        self.assertEqual(
            header.goods,
            20 * 100
        )
        self.assertEqual(
            header.vat,
            20 * 0
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
            20 + 20
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                0
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (2 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                None
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (2 * i) + 1 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )            
            
        # assuming the lines are created in the same order
        # as the nominal entries....
        goods_trans = nom_trans[::2]
        total_trans = nom_trans[1::2]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * 100
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        for i, vat_tran in enumerate(vat_transactions):
            vat_tran.header = header.pk
            vat_tran.line = lines[i].pk
            vat_tran.module = "PL"
            vat_tran.ref = header.ref
            vat_tran.period = header.period
            vat_tran.date = header.date
            vat_tran.field = "v"
            vat_tran.tran_type = header.type
            vat_tran.vat_type = "i"
            vat_tran.vat_code = lines[i].vat_code
            vat_tran.vat_rate = lines[i].vat_code.rate
            vat_tran.vat = 0 # double check
            vat_tran.goods = lines[i].goods
            vat_tran.vat = lines[i].vat

    # CORRECT USAGE
    # VAT only invoice
    # I.e. goods = 0 and vat = 20 on each analysis line
    def test_vat_only_lines_invoice(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'goods': 0,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            header.total,
            20 * (0 + 20)
        )
        self.assertEqual(
            header.goods,
            0 * 100
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
            20 + 20
            # i.e. 0 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entry for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

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
                0
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
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
                nom_trans[ (2 * i) + 0 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (2 * i) + 1 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        vat_trans = nom_trans[::2]
        total_trans = nom_trans[1::2]

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * 20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        for i, vat_tran in enumerate(vat_transactions):
            vat_tran.header = header.pk
            vat_tran.line = lines[i].pk
            vat_tran.module = "PL"
            vat_tran.ref = header.ref
            vat_tran.period = header.period
            vat_tran.date = header.date
            vat_tran.field = "v"
            vat_tran.tran_type = header.type
            vat_tran.vat_type = "i"
            vat_tran.vat_code = lines[i].vat_code
            vat_tran.vat_rate = lines[i].vat_code.rate
            vat_tran.goods = 0
            vat_tran.goods = lines[i].goods
            vat_tran.vat = lines[i].vat

    # CORRECT USAGE
    # Zero value invoice
    # So analysis must cancel out
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_analysis(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 20,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 10
        line_forms += (
            [{
                'description': self.description,
                'goods': -20,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': +20
            }] * 10
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
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
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        vat_transactions_orig = vat_transactions
        vat_transactions = vat_transactions_orig[:10]

        lines_orig = lines
        lines = lines_orig[:10]

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            40
            # i.e. 20 nominal trans for goods
            # i.e. 20 nominal trans for vat
            # no nominal control account nominal entry because would be zero value -- WHAT THE WHOLE TEST IS ABOUT !!!
        )
        # assuming the lines are created in the same order
        # as the nominal entries....

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
                20
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (2 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (2 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        lines = lines_orig[10:]
        vat_transactions = vat_transactions_orig
        for i, line in enumerate(lines, 10):
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
                -20
            )
            self.assertEqual(
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (2 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (2 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                None
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
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

        goods_and_vat_nom_trans = nom_trans[:40]
        positive_goods_trans = goods_and_vat_nom_trans[:20:2]
        negative_vat_trans = goods_and_vat_nom_trans[1:20:2]
        negative_goods_trans = goods_and_vat_nom_trans[20::2]
        positive_vat_trans = goods_and_vat_nom_trans[21::2]

        lines = lines_orig[:10]
        for i, tran in enumerate(positive_goods_trans):
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )
        lines = lines_orig[:10]
        for i, tran in enumerate(negative_vat_trans):
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        lines = lines_orig[10:]
        for i, tran in enumerate(negative_goods_trans):
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )
        lines = lines_orig[10:]
        for i, tran in enumerate(positive_vat_trans):
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        lines = lines_orig[:10]
        vat_transactions = vat_transactions_orig[:10]

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        lines = lines_orig[10:]
        vat_transactions = vat_transactions_orig[10:]

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )


    # CORRECT USAGE
    # Zero value invoice again but this time with no lines
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_no_analysis(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            0
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
            # i.e. 20 nominal trans for goods
            # i.e. 20 nominal trans for vat
            # no nominal control account nominal entry because would be zero value -- WHAT THE WHOLE TEST IS ABOUT !!!
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

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
        )


    # INCORRECT USAGE
    # No point allowing lines which have no goods or vat
    def test_zero_invoice_with_line_but_goods_and_zero_are_both_zero(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': 0,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
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
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 2400})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

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
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (100 + 20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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
            headers[0] # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            -2400
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

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
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )


        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (100 + 20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    # INCORRECT USAGE
    # For an invoice of 2400 the match value must be between 0 and -2400 
    def test_match_total_greater_than_zero(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(self.supplier, "invoice to match", 1, 2000)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0.01})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
        )

    # INCORRECT USAGE
    # Try and match -2400.01 to an invoice for 2400
    def test_match_total_less_than_invoice_total(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "invoice to match", 1, 2500)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 2400.01})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
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
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, 2400)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 1200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )

        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

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
                line.nominal,
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (100 + 20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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
            headers[0] # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    """
    Test negative invoices now.  I've not repeated all the tests
    that were done for positives.  We shouldn't need to.
    """

    # CORRECT USAGE
    def test_negative_invoice_entered_without_matching(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            header.total
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (-100 + -20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    # CORRECT USAGE
    def test_negative_invoice_without_matching_with_total(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            header.total
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (-100 + -20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    """
    Test matching negative invoices now
    """

    # CORRECT USAGE
    def test_fully_matching_a_negative_invoice_NEGATIVE(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0] # NEGATIVE PAYMENT
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -2400})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (-100 + -20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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
            headers[0] # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            2400
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

    # CORRECT USAGE
    def test_selecting_a_transaction_to_match_but_for_zero_value_against_negative_invoice_NEGATIVE(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0] # NEGATIVE PAYMENT
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (-100 + -20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # INCORRECT USAGE
    # For an invoice of 2400 the match value must be between 0 and -2400 
    def test_match_total_less_than_zero_NEGATIVE(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        invoice_to_match = create_invoices(self.supplier, "invoice to match", 1, -2000)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -0.01})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
        )

    # INCORRECT USAGE
    # Try and match -2400.01 to an invoice for 2400
    def test_match_total_less_than_invoice_total_NEGATIVE(self):
        self.client.force_login(self.user)

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "invoice to match", 1, -2500)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -2400.01})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
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
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0
            }
        )
        data.update(header_data)
        payment = create_payments(self.supplier, "payment", 1, -2400)[0]
        headers_as_dicts = [ to_dict(payment) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -1200})
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        line_forms = ([{
                'description': self.description,
                'goods': -100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
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
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
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
                self.nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ (3 * i) + 0 ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_trans = nom_trans[::3]
        vat_trans = nom_trans[1::3]
        total_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
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
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'g'
            )

        for i, tran in enumerate(vat_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.value,
                -20
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
            )     
            self.assertEqual(
                tran.date,
                header.date
            )
            self.assertEqual(
                tran.field,
                'v'
            )

        for i, tran in enumerate(total_trans):
            self.assertEqual(
                tran.module,
                PL_MODULE
            )
            self.assertEqual(
                tran.header,
                header.pk
            )
            self.assertEqual(
                tran.line,
                lines[i].pk
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.value,
                -1 * (-100 + -20)
            )
            self.assertEqual(
                tran.ref,
                header.ref
            )
            self.assertEqual(
                tran.period,
                PERIOD
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
            headers[0] # payment created first before invoice
        )
        self.assertEqual(
            matches[0].value,
            1200
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

"""
EDIT
"""

class EditInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
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


    # CORRECT USAGE
    # add a new matching transaction for 0 value
    # edit an existing to zero value
    def test_match_value_of_zero_is_removed_where_edit_tran_is_matched_by_for_all_match_records(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1200
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally
        matching_forms[-1]["value"] = 0
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects(
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": 0}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, -1000)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 600)
        self.assertEqual(headers[1].due, 600)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        line_no = 1
        for line in lines:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)


    def test_match_value_of_zero_is_removed_where_edit_tran_is_not_matched_by_for_all_match_records(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1200
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 0}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 0
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, -1000)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 0)
        self.assertEqual(headers[1].due, 1200)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, 0)
        self.assertEqual(headers[2].due, -1200)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 0)

    # CORRECT USAGE
    def test_get_request(self):
        self.client.force_login(self.user)
        transaction = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="ref",
            date=self.date,
            due_date=self.due_date,
            total=120,
            goods=100,
            vat=20
        )
        url = reverse("purchases:edit", kwargs={"pk": transaction.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" disabled required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi" selected>Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )



    # CORRECT USAGE
    # Invoice total is increased (the invoice this time is the matched_to transaction)
    # Lines are added to match the header total
    # Payment was previously fully matched
    def test_line_no_changed(self):
        self.client.force_login(self.user)
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines_orig = lines
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].pk, invoices[0].pk)
        self.assertEqual(headers[0].total, 1200)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, 1200)

        line_no = 1
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1200
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])

        lines_as_dicts = [ to_dict(line) for line in lines ]
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = lines_as_dicts
        line_no = 1
        # THIS MIRRORS WHAT WOULD HAPPEN THROUGH THE UI
        # THE API IS A DIFFERENT STORY THOUGH
        # THE USER WOULD WANT TO JUST CHANGE THE LINE_NO OF THE LINE
        # AND NOT HAVE TO SET THE ORDER FOR THE OTHERS
        for line_form in line_forms:
            line_form["ORDER"] = line_no
            line_no = line_no + 1
        line_forms[-2]["ORDER"] = 10
        line_forms[-1]["ORDER"] = 9
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)


        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].pk, invoices[0].pk)
        self.assertEqual(headers[0].total, 1200)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, 1200)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)

        line_no = 1
        for index, line in enumerate(lines[:8]):
            self.assertEqual(line.pk, lines_orig[index].pk)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        self.assertEqual(lines[8].pk, lines_orig[-1].pk)
        
        self.assertEqual(lines[8].description, self.description)
        self.assertEqual(lines[8].goods, 100)
        self.assertEqual(lines[8].nominal, self.nominal)
        self.assertEqual(lines[8].vat_code, self.vat_code)
        self.assertEqual(lines[8].vat, 20)
        self.assertEqual(lines[8].line_no, 9)

        self.assertEqual(lines[9].pk, lines_orig[-2].pk)
        
        self.assertEqual(lines[9].description, self.description)
        self.assertEqual(lines[9].goods, 100)
        self.assertEqual(lines[9].nominal, self.nominal)
        self.assertEqual(lines[9].vat_code, self.vat_code)
        self.assertEqual(lines[9].vat, 20)
        self.assertEqual(lines[9].line_no, 10)
        


    # CORRECT USAGE
    # Invoice total is increased (the invoice this time is the matched_to transaction)
    # Lines are added to match the header total
    # Payment was previously fully matched
    def test_line_delete_line(self):
        self.client.force_login(self.user)
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines_orig = lines
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].pk, invoices[0].pk)
        self.assertEqual(headers[0].total, 1200)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, 1200)

        line_no = 1
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])


        lines_as_dicts = [ to_dict(line) for line in lines ]
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = lines_as_dicts
        line_no = 1

        # THIS MIRRORS WHAT WOULD HAPPEN THROUGH THE UI
        # THE API IS A DIFFERENT STORY THOUGH
        # THE USER WOULD WANT TO JUST CHANGE THE LINE_NO OF THE LINE
        # AND NOT HAVE TO SET THE ORDER FOR THE OTHERS

        # DELETING A LINE IN THE UI MUST REORDER TOO
        for line_form in line_forms:
            line_form["ORDER"] = line_no
            line_no = line_no + 1
        line_forms[-2]["DELETE"] = 'yes'
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)

        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].pk, invoices[0].pk)
        self.assertEqual(headers[0].total, 1080)
        self.assertEqual(headers[0].paid, 0)
        self.assertEqual(headers[0].due, 1080)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 9)

        line_no = 1
        for index, line in enumerate(lines[:8]):
            self.assertEqual(line.pk, lines_orig[index].pk)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        self.assertEqual(lines[8].pk, lines_orig[-1].pk)
        
        self.assertEqual(lines[8].description, self.description)
        self.assertEqual(lines[8].goods, 100)
        self.assertEqual(lines[8].nominal, self.nominal)
        self.assertEqual(lines[8].vat_code, self.vat_code)
        self.assertEqual(lines[8].vat, 20)
        self.assertEqual(lines[8].line_no, 9)


    # INCORRECT USAGE
    # header is invalid but lines and matching are ok
    def test_header_is_invalid_but_lines_and_matching_are_ok(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": 999999999999,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2400
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 20
                }
        ] * 10
        line_forms = line_trans + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        # TO BE CLEAR - We are doubling the invoice

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        


    # CORRECT USAGE
    # Invoice total is increased (the invoice this time is the matched_to transaction)
    # Lines are added to match the header total
    # Payment was previously fully matched
    def test_1(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2400
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600

        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 20
                }
        ] * 10
        line_forms = line_trans + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        # TO BE CLEAR - We are doubling the invoice

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 1200)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)


    # CORRECT USAGE -
    # Same as above only this time the increase comes from increasing an existing line
    # rather than adding new ones
    def test_2(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 200
        line_trans[-1]["vat"] = 40
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        # TO BE CLEAR - We are doubling the invoice

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 120)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines[:-2]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600) 


    # INCORRECT USAGE
    # Delete a line so the total decreases
    # But matching, which previously fully paid the invoice, is not adjusted
    def test_3(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600) 

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1080.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # Same as above but this time we lower the line value rather than delete a line
    def test_4(self):
        self.client.force_login(self.user)
        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 0
        line_trans[-1]["vat"] = 0
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Goods and Vat cannot both be zero.</li>',
            html=True
        )



    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is still fully matched
    def test_5(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2200
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[0]["value"] = -1200
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 1000
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 10
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2200)
        self.assertEqual(headers[1].paid, 2200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1200)
        self.assertEqual(headers[2].due, 0)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:10]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -1200)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -1000) 

    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is not still fully matched
    def test_6(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2200
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[0]["value"] = -1100
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 1000
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 10
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2200)
        self.assertEqual(headers[1].paid, 2100)
        self.assertEqual(headers[1].due, 100)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1100)
        self.assertEqual(headers[2].due, -100)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:10]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -1100)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -1000) 

    # CORRECT USAGE
    # Invoice total is increased by increasing existing line
    # Invoice is still fully matched
    def test_7(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -660})
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 660
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -660)
        self.assertEqual(headers[0].due, -340)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1320)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -660)
        self.assertEqual(headers[2].due, -540)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)
        
        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -660)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -660) 

    # CORRECT USAGE
    # Invoice total is increased by increasing existing line
    # Invoice is not fully matched now though -- difference to above
    def test_8(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -660})
        matching_forms[1]["value"] = 600
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1260)
        self.assertEqual(headers[1].due, 60)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -660)
        self.assertEqual(headers[2].due, -540)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)
        
        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -660)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)


    # INCORRECT USAGE
    # Payment total is increased by adding new lines
    # But we overmatch so it does not work
    def test_9(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2100
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[0]["value"] = -1200
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 1000
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 9
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2100.00</li>',
            html=True
        )

    # INCORRECT USAGE
    # Same test as above except we increase the invoice by increasing an existing line value this time
    def test_10(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -700})
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 700
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1320.00</li>',
            html=True
        )


    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_11(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally
        matching_forms[-1]["value"] = 480

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -480)
        self.assertEqual(headers[0].due, -520)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1080)
        self.assertEqual(headers[1].paid, 1080)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 9)

        line_no = 1
        for line in lines:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -480)


    # CORRECT USAGE
    # Decrease line value so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_12(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 540
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10 
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -540)
        self.assertEqual(headers[0].due, -460)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 1140)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        line_no = 1
        for line in lines[:-1]:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)
        

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -540)

    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching such that the invoice is not fully paid anymore
    def test_13(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1200.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -500}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 500
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -500)
        self.assertEqual(headers[0].due, -500)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1080)
        self.assertEqual(headers[1].paid, 1000)
        self.assertEqual(headers[1].due, 80)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -500)
        self.assertEqual(headers[2].due, -700)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 9)

        line_no = 1
        for line in lines:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -500)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -500)

    # CORRECT USAGE
    # Decrease line value so the total decreases - like test_3
    # But this time we lower the matching so that is isn't fully paid
    def test_14(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -500}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 500
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10 
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -500)
        self.assertEqual(headers[0].due, -500)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 1000)
        self.assertEqual(headers[1].due, 140)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -500)
        self.assertEqual(headers[2].due, -700)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        line_no = 1
        for line in lines[:-1]:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)
        

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -500)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -500)

    # INCORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # Match values are ok from POV of the matched_to transaction
    # But the matched_value is now not ok for the invoice
    def test_15(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1200.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -700})

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 700
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1080.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # Decrease line value so the total decreases
    # Matching is not right though
    def test_16(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -700}) # Same value as matched originally

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 700
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1140.00</li>',
            html=True
        )


    # Same as test_5 but this time we match a new transaction
    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is still fully matched
    def test_17(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2200
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[0]["value"] = -1000
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 1000
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )

        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]

        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 10
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2200)
        self.assertEqual(headers[1].paid, 2200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1000)
        self.assertEqual(headers[2].due, -200)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -200)
        self.assertEqual(headers[3].due, -1000)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:10]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -1000)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -1000) 
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -200)

    # same as test_6 except this time we match a new transaction
    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is not still fully matched
    def test_18(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2200
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[0]["value"] = -1000
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 1000
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 10
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2200)
        self.assertEqual(headers[1].paid, 2100)
        self.assertEqual(headers[1].due, 100)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1000)
        self.assertEqual(headers[2].due, -200)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -100)
        self.assertEqual(headers[3].due, -1100)


        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:10]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -1000)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -1000)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -100)

    # Same test as 7 but matching a new transaction this time
    # CORRECT USAGE
    # Invoice total is increased by increasing existing line
    # Invoice is still fully matched
    def test_19(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -620})
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 620
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -80}
        )

        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -620)
        self.assertEqual(headers[0].due, -380)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1320)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -620)
        self.assertEqual(headers[2].due, -580)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -80)
        self.assertEqual(headers[3].due, -1120)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)
        
        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -620)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -620)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -80)

    # same as test_8 but this time we create a new transaction
    # CORRECT USAGE
    # Invoice total is increased by increasing existing line
    # Invoice is not fully matched now though -- difference to above
    def test_20(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -640})
        matching_forms[1]["value"] = 600
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -60}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1300)
        self.assertEqual(headers[1].due, 20)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -640)
        self.assertEqual(headers[2].due, -560)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -60)
        self.assertEqual(headers[3].due, -1140)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)
        
        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -640)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -60)

    # test_9 again but creating a new transaction this time
    # INCORRECT USAGE
    # Payment total is increased by adding new lines
    # But we overmatch so it does not work
    def test_21(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 2100
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -1000})
        matching_forms[1]["value"] = 1000
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ] * 9
        line_forms = lines_as_dicts + new_lines
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2100.00</li>',
            html=True
        )


    # test_10 again but this time creating a new transaction
    # INCORRECT USAGE
    # Same test as above except we increase the invoice by increasing an existing line value this time
    def test_22(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600})
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 600
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        lines_as_dicts[-1]["goods"] = 200
        lines_as_dicts[-1]["vat"] = 40
        line_forms = lines_as_dicts
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)


        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1320.00</li>',
            html=True
        )


    # test_11 again but this time creating a new matching transaction
    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_23(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally
        matching_forms[1]["value"] = 400
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -80}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -400)
        self.assertEqual(headers[0].due, -600)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1080)
        self.assertEqual(headers[1].paid, 1080)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -80)
        self.assertEqual(headers[3].due, -1120)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 9)

        line_no = 1
        for line in lines:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -400)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -80)

    # test_12 but this time we match a new transaction
    # CORRECT USAGE
    # Decrease line value so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_24(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -600}) # Same value as matched originally
        matching_forms[-1]["value"] = 500
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -40}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10 
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -500)
        self.assertEqual(headers[0].due, -500)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 1140)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -40)
        self.assertEqual(headers[3].due, -1160)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        line_no = 1
        for line in lines[:-1]:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)
        

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -500)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -40)

    # test_13 again but this time with a new matching transaction
    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching such that the invoice is not fully paid anymore
    def test_25(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1200.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -480}) # Same value as matched originally
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 480
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -480)
        self.assertEqual(headers[0].due, -520)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1080)
        self.assertEqual(headers[1].paid, 1060)
        self.assertEqual(headers[1].due, 20)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -480)
        self.assertEqual(headers[2].due, -720)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -100)
        self.assertEqual(headers[3].due, -1100)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 9)

        line_no = 1
        for line in lines:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -480)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -480)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -100)

    # test_14 again but this time we create a new matching transaction
    # CORRECT USAGE
    # Decrease line value so the total decreases - like test_3
    # But this time we lower the matching so that is isn't fully paid
    def test_26(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -450}) # Same value as matched originally
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 450
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10 
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -450)
        self.assertEqual(headers[0].due, -550)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 1000)
        self.assertEqual(headers[1].due, 140)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -450)
        self.assertEqual(headers[2].due, -750)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, -100)
        self.assertEqual(headers[3].due, -1100)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        line_no = 1
        for line in lines[:-1]:
            self.assertEqual(line.line_no, line_no)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)
        

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -450)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -450)
        self.assertEqual(matches[2].matched_by, invoices[0])
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, -100)

    # test 15 again but this time we add a new matching transaction
    # INCORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # Match values are ok from POV of the matched_to transaction
    # But the matched_value is now not ok for the invoice
    def test_27(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1200.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1080
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -700})
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 700
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["DELETE"] = 'yes' # DELETE THE LAST LINE
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1080.00</li>',
            html=True
        )

    # test_16 again but this time we create a new matching transaction
    # INCORRECT USAGE
    # Decrease line value so the total decreases
    # Matching is not right though
    def test_28(self):
        self.client.force_login(self.user)

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        invoices += create_invoices(self.supplier, "invoice", 2, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(invoices[0], [ (invoices[1], -600), (payment, -600) ] )
        matching_trans = [ invoices[1], payment ]

        # MATCH A 1000.00 invoice to a -1000 invoice and 1000 payment; 600.00 of each is matched

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": "invoice1",
                "date": invoices[0].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        _matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(_matching_trans, {"id": "matched_to"}, {"value": -700}) # Same value as matched originally
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_forms[1]["value"] = 700
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -600)
        self.assertEqual(headers[2].due, -600)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -600)
        self.assertEqual(matches[1].matched_by, invoices[0])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1140.00</li>',
            html=True
        )

    """
    So far we have tested only editing invoices where the matching records have
    this same invoice as matched_by.  Now we test editing the matching for
    an invoice where it has a matched transaction where the invoice is the matched_to
    in the relationship
    """

    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    def test_29(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        # invoice 1
        # invoice 2
        # -200

        # payment
        # invoice 1
        # 600

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1200
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 800
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 1000)
        self.assertEqual(headers[1].due, 200)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 800)   

    # CORRECT USAGE
    # WE DECREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    def test_30(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1200
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 100
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -100)
        self.assertEqual(headers[0].due, -900)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 300)
        self.assertEqual(headers[1].due, 900)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 100)

    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # ALSO INCREASE THE HEADER
    def test_31(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1320
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 1000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 200
        line_trans[-1]["vat"] = 40
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1320)
        self.assertEqual(headers[1].paid, 1200)
        self.assertEqual(headers[1].due, 120)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 200)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 40)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 1000)

    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # AND DECREASE THE HEADER
    def test_32(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 940
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -940)
        self.assertEqual(headers[0].due, -60)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 1140)
        self.assertEqual(headers[1].due, 0)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 940)

    # CORRECT USAGE
    # WE DECREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # AND DECREASE THE HEADER
    def test_33(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 100
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -100)
        self.assertEqual(headers[0].due, -900)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1140)
        self.assertEqual(headers[1].paid, 300)
        self.assertEqual(headers[1].due, 840)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines[:9]:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        
        self.assertEqual(line.description, self.description)
        self.assertEqual(line.goods, 50)
        self.assertEqual(line.nominal, self.nominal)
        self.assertEqual(line.vat_code, self.vat_code)
        self.assertEqual(line.vat, 10)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 100)

    # INCORRECT USAGE
    # Same as test_33 but we just try and match a value wrongly - incorrect sign
    def test_34(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = -100 # THIS IS WRONG.  SHOULD BE A POSITIVE.
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)

        self.assertContains(
            response,
            '<li class="py-1">Value must be between 0 and 1000.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # Same as above two tests but this time we do incorrect matching overall i.e. match is ok at match record level when taken in isolation
    def test_35(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 1000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # SO TRYING TO MATCH -1200 to a 1140 invoice which is wrong

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1140.00</li>',
            html=True
        )

    # NOW I CHECK AN INVALID HEADER, INVALID LINES AND INVALID MATCHING
    # AGAIN JUST USE TEST_33 AS A BASE

    # INCORRECT USAGE
    # INVALID HEADER
    def test_36(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": 999999999, # INVALID SUPPLIER PRIMARY KEY VALUE
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 600
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)

        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )


    # INCORRECT USAGE
    # INVALID LINES
    def test_37(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 600
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_trans[-1]["nominal"] = 99999999
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)

        self.assertContains(
            response,
            '<li class="py-1">Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )

    # INCORRECT USAGE
    # INVALID MATCHING.  Already covered i think but include it here just so next to the other two tests.
    def test_38(self):
        self.client.force_login(self.user)

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ]
            * 10
        )
        # SECOND INVOICE
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(invoices[0], [ (invoices[1], -200) ] ) # FIRST MATCH
        invoices[0] = match_by
        invoices[1] = match_to[0]
        match_by, match_to = match(payment, [ (invoices[0], 600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)   
    
        url = reverse("purchases:edit", kwargs={"pk": invoices[0].pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
                "ref": headers[1].ref,
                "date": headers[1].date,
                "total": 1140
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[1], payment ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": -200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = invoices[0].pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 2000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 50
        line_trans[-1]["vat"] = 10
        line_forms = line_trans

        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 10
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -400)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 800)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -200)
        self.assertEqual(headers[2].due, -1000)

        lines = list(PurchaseLine.objects.all())
        self.assertEqual(len(lines), 10)

        for line in lines:
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, invoices[0])
        self.assertEqual(matches[0].matched_to, invoices[1])
        self.assertEqual(matches[0].value, -200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[0])
        self.assertEqual(matches[1].value, 600)

        self.assertContains(
            response,
            '<li class="py-1">Value must be between 0 and 1000.00</li>',
            html=True
        )


class EditInvoiceNominalEntries(TestCase):

    """
    Based on same tests as CreateInvoiceNominalEntries
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


    # CORRECT USAGE
    # Basic edit here in so far as we just change a line value
    def test_nominals_created_for_lines_with_goods_and_vat_above_zero(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total - 60 # we half the goods and vat for a line
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 50
        line_forms[-1]["vat"] = 10
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
            2340
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2340
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
        vat_transactions = list(vat_transactions)
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.line_no, i + 1)
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, 50)
        self.assertEqual(edited_line.nominal, self.nominal)
        self.assertEqual(edited_line.vat_code, self.vat_code)
        self.assertEqual(edited_line.vat, 10)
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            nom_trans[ 57 ]
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            nom_trans[ 58 ]
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            nom_trans[ 59 ]
        )
        self.assertEqual(
            edited_line.vat_transaction,
            vat_transactions[-1]
        )        

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        unedited_goods_nom_trans = goods_nom_trans[:-1]

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        unedited_vat_nom_trans = vat_nom_trans[:-1]

        for tran in unedited_vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        unedited_total_nom_trans = total_nom_trans[:-1]

        for tran in unedited_total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        # NOW CHECK THE EDITED

        edited_goods_nom_tran = goods_nom_trans[-1]
        self.assertEqual(
            edited_goods_nom_tran.value,
            50
        )
        self.assertEqual(
            edited_goods_nom_tran.nominal,
            self.nominal
        )
        self.assertEqual(
            edited_goods_nom_tran.field,
            "g"
        )

        edited_vat_nom_tran = vat_nom_trans[-1]
        self.assertEqual(
            edited_vat_nom_tran.value,
            10
        )
        self.assertEqual(
            edited_vat_nom_tran.nominal,
            self.vat_nominal
        )
        self.assertEqual(
            edited_vat_nom_tran.field,
            "v"
        )

        edited_total_nom_tran = total_nom_trans[-1]
        self.assertEqual(
            edited_total_nom_tran.value,
            -60
        )
        self.assertEqual(
            edited_total_nom_tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            edited_total_nom_tran.field,
            "t"
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    # CORRECT USAGE
    # Add another line this time
    def test_nominals_created_for_new_line(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total + 120 # we half the goods and vat for a line
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        last_line_form = line_forms[-1].copy()
        last_line_form["id"] = ""
        line_forms.append(last_line_form)
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
            2520
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2520
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            21 + 21 + 21
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            21
        )
        lines = list(lines)

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            21
        )

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for tran in goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        for tran in vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        for tran in total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        # NOW CHECK THE EDITED

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    # CORRECT USAGE
    # Based on above
    # Except this time we reduce goods to zero on a line
    # This should delete the corresponding nominal transaction for goods
    # And obviously change the control account nominal value
    def test_goods_reduced_to_zero_but_vat_non_zero_on_a_line(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total - 100 # we set goods = 0 when previously was 100
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 20
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
            2300
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2300
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            19 + 20 + 20
            # 19 goods nominal transactions
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        header = headers[0]
        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.line_no, i + 1)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, 0)
        self.assertEqual(edited_line.nominal, self.nominal)
        self.assertEqual(edited_line.vat_code, self.vat_code)
        self.assertEqual(edited_line.vat, 20)
        # NOMINAL TRANSACTION FOR GOODS IS REMOVED
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            nom_trans[ 57 ]
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            nom_trans[ 58 ]
        )
        self.assertEqual(
            edited_line.vat_transaction,
            vat_transactions[i]
        )

        goods_nom_trans = nom_trans[:-2:3]
        vat_nom_trans = nom_trans[1:-2:3]
        total_nom_trans = nom_trans[2:-2:3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        unedited_vat_nom_trans = vat_nom_trans

        for tran in unedited_vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        unedited_total_nom_trans = total_nom_trans

        for tran in unedited_total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        # NOW CHECK THE EDITED

        edited_vat_nom_tran = nom_trans[-2]
        self.assertEqual(
            edited_vat_nom_tran.value,
            20
        )
        self.assertEqual(
            edited_vat_nom_tran.nominal,
            self.vat_nominal
        )
        self.assertEqual(
            edited_vat_nom_tran.field,
            "v"
        )

        edited_total_nom_tran = nom_trans[-1]
        self.assertEqual(
            edited_total_nom_tran.value,
            -20
        )
        self.assertEqual(
            edited_total_nom_tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            edited_total_nom_tran.field,
            "t"
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

            self.assertEqual(
                header.goods,
                sum( vat_tran.goods for vat_tran in vat_transactions)
            )

            self.assertEqual(
                header.vat,
                sum( vat_tran.vat for vat_tran in vat_transactions)
            )

    # CORRECT USAGE
    # Same as above except we now blank out vat and not goods
    def test_vat_reduced_to_zero_but_goods_non_zero_on_a_line(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
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
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total - 20 # we set vat = 0 when previously was 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 100
        line_forms[-1]["vat"] = 0
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
            2380
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2380
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 19 + 20
            # 19 goods nominal transactions
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        i = i + 1

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.line_no, i + 1)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, 100)
        self.assertEqual(edited_line.nominal, self.nominal)
        self.assertEqual(edited_line.vat_code, self.vat_code)
        self.assertEqual(edited_line.vat, 0)
        # NOMINAL TRANSACTION FOR GOODS IS REMOVED
        self.assertEqual(
            edited_line.goods_nominal_transaction,
            nom_trans[ 57 ]
        )
        self.assertEqual(
            edited_line.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            edited_line.total_nominal_transaction,
            nom_trans[ 58 ]
        )
        self.assertEqual(
            edited_line.vat_transaction,
            vat_transactions[i]
        )

        goods_nom_trans = nom_trans[:-2:3]
        vat_nom_trans = nom_trans[1:-2:3]
        total_nom_trans = nom_trans[2:-2:3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        unedited_vat_nom_trans = vat_nom_trans

        for tran in unedited_vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        unedited_total_nom_trans = total_nom_trans

        for tran in unedited_total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        # NOW CHECK THE EDITED

        edited_goods_nom_tran = nom_trans[-2]
        self.assertEqual(
            edited_goods_nom_tran.value,
            100
        )
        self.assertEqual(
            edited_goods_nom_tran.nominal,
            self.nominal
        )
        self.assertEqual(
            edited_goods_nom_tran.field,
            "g"
        )

        edited_total_nom_tran = nom_trans[-1]
        self.assertEqual(
            edited_total_nom_tran.value,
            -100
        )
        self.assertEqual(
            edited_total_nom_tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            edited_total_nom_tran.field,
            "t"
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    # CORRECT USAGE
    # Zero out the goods and the vat
    # We expect the line and the three nominal transactions to all be deleted
    def test_goods_and_vat_for_line_reduced_to_zero(self):
        self.client.force_login(self.user)
 
        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")
        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total - 120 # we set vat = 0 when previously was 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 0
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<li class="py-1">Goods and Vat cannot both be zero.</li>',
            html=True
        )

    # CORRECT USAGE
    # SIMPLY MARK A LINE AS DELETED
    def test_line_marked_as_deleted_has_line_and_nominals_removed(self):
        self.client.force_login(self.user)
 
        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total - 120 # we set vat = 0 when previously was 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 100
        line_forms[-1]["vat"] = 20
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
            2280
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2280
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            19 + 19 + 19
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            19
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            19
        )

        lines = list(lines)
        unedited_lines = list(lines)[:-1]
        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no , i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        unedited_vat_nom_trans = vat_nom_trans

        for tran in unedited_vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        unedited_total_nom_trans = total_nom_trans

        for tran in unedited_total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    # CORRECT USAGE
    # DELETE ALL THE LINES SO IT IS A ZERO INVOICE
    def test_non_zero_invoice_is_changed_to_zero_invoice_by_deleting_all_lines(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )
        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]
        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": 0
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        for form in line_forms:
            form["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        # WE HAVE TO MATCH OTHERWISE IT WILL ERROR
        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
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
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
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

    # CORRECT USAGE
    def test_change_zero_invoice_to_a_non_zero_invoice(self):
        self.client.force_login(self.user)

        header = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "paid": 0,
                "due": 0
            }
        )

        headers_to_match_against = create_cancelling_headers(2, self.supplier, "match", "pi", 100)
        match(header, [ (headers_to_match_against[0], 100), (headers_to_match_against[1], -100) ] )

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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": 2400
            }
        )
        data.update(header_data)
        line_forms = [
                {
                    
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 20
                }
        ] * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

        # WE HAVE TO MATCH OTHERWISE IT WILL ERROR
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects([headers_to_match_against[1]], {"id": "matched_to"}, {"value": -100})
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all().order_by("pk")
        header = headers[0]
        self.assertEqual(
            len(headers),
            3
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
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


        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_1(self):
        self.client.force_login(self.user)

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
                "type": "pc",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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

        # Invoice for -0.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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
            "total": headers[1].total * -1, # I.E. VIEWED AS POSITIVE IN UI
            "paid": headers[1].paid * -1, # I.E. VIEWED AS POSITIVE IN UI
            "due": headers[1].due * -1, # I.E. VIEWED AS POSITIVE IN UI
            "matched_by": '', 
            "matched_to": headers[1].pk, # I.E. VIEWED AS POSITIVE IN UI
            "value": headers[1].total * -1, # I.E. VIEWED AS POSITIVE IN UI
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

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 20
                }
        ]
        line_forms[0]["id"] = lines[0].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1 
        data.update(line_data)

        matching_forms = []
        # Matched to the invoice for 0.01

        matching_forms.append({
            "type": headers[2].type,
            "ref": headers[2].ref,
            "total": headers[2].total * -1,
            "paid": headers[2].paid * -1,
            "due": headers[2].due * -1,
            "matched_by": headers[2].pk,
            "matched_to": headers[0].pk,
            "value": '-110',
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )


    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_2(self):
        self.client.force_login(self.user)

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
                "type": "pc",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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

        # Invoice for -0.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_3(self):
        self.client.force_login(self.user)

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
                "type": "pc",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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

        # Invoice for -0.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
            "value": '0',
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_4(self):
        self.client.force_login(self.user)

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
                "type": "pc",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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

        # Invoice for -0.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
                    'vat': 0
                }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)

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

        lines = PurchaseLine.objects.filter(header=headers[0]).all()
        self.assertEqual(
            len(lines),
            1
        )

        # Invoice for 120.01
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
                "supplier": self.supplier.pk,
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
                    'nominal': self.nominal.pk,
                    'vat_code': self.vat_code.pk,
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
            "value": '0.01',
            "id": matches[0].pk
        })
        matching_data = create_formset_data(match_form_prefix, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )


    # INCORRECT USAGE
    # Add another line this time
    def test_new_line_marked_as_deleted_does_not_count(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        last_line_form = line_forms[-1].copy()
        last_line_form["id"] = ""
        last_line_form["DELETE"] = "YEP"
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
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
        lines = list(lines)

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )
            
        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for tran in goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )

        for tran in vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )

        for tran in total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )

        # NOW CHECK THE EDITED

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

    def test_edit_header_only(self):
        # change the period only and check that it feeds through to the NL and VT
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "goods": 2000,
                "vat": 400,
                "period": PERIOD
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
            self.purchase_control
        )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )
        self.assertEqual(
            headers[0].period,
            "202007"
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                header.period
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                lines[i].goods_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.period,
                "202007"
            )

        for i, tran in enumerate(vat_nom_trans):
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                lines[i].vat_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.period,
                "202007"
            )

        for i, tran in enumerate(total_nom_trans):
            self.assertEqual(
                tran.value,
                -120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
            )
            self.assertEqual(
                tran.period,
                "202007"
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
                "ref": header.ref,
                "date": header.date,
                "due_date": header.due_date,
                "total": header.total,
                "period": "202008" # CHANGE THE PERIOD ONLY IN THIS EDIT
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id',  'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
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
            2400
        )
        self.assertEqual(
            headers[0].paid,
            0
        )
        self.assertEqual(
            headers[0].due,
            2400
        )
        self.assertEqual(
            headers[0].period,
            "202008"
        )

        nom_trans = NominalTransaction.objects.all()
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = (
            PurchaseLine.objects
            .select_related("vat_code")
            .all()
            .order_by("pk")
        )
        self.assertEqual(
            len(lines),
            20
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            20
        )
        vat_transactions = list(vat_transactions)
        lines = list(lines)

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[ 3 * i ]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[ (3 * i) + 1 ]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[ (3 * i) + 2 ]
            )
            self.assertEqual(
                line.vat_transaction,
                vat_transactions[i]
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for tran in goods_nom_trans:
            self.assertEqual(
                tran.value,
                100
            )
            self.assertEqual(
                tran.nominal,
                self.nominal
            )
            self.assertEqual(
                tran.field,
                "g"
            )
            self.assertEqual(
                tran.period,
                "202008"
            )

        for tran in vat_nom_trans:
            self.assertEqual(
                tran.value,
                20
            )
            self.assertEqual(
                tran.nominal,
                self.vat_nominal
            )
            self.assertEqual(
                tran.field,
                "v"
            )
            self.assertEqual(
                tran.period,
                "202008"
            )

        for tran in total_nom_trans:
            self.assertEqual(
                tran.value,
                -1 * 120
            )
            self.assertEqual(
                tran.nominal,
                self.purchase_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                tran.period,
                "202008"
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )

        for i, vat_tran in enumerate(vat_transactions):
            self.assertEqual(
                vat_tran.header,
                header.pk
            )
            self.assertEqual(
                vat_tran.line,
                lines[i].pk
            )
            self.assertEqual(
                vat_tran.module,
                "PL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                "202008"
            )
            self.assertEqual(
                vat_tran.date,
                header.date
            )
            self.assertEqual(
                vat_tran.field,
                "v"
            )
            self.assertEqual(
                vat_tran.tran_type,
                header.type
            )
            self.assertEqual(
                vat_tran.vat_type,
                "i"
            )
            self.assertEqual(
                vat_tran.vat_code,
                lines[i].vat_code
            )
            self.assertEqual(
                vat_tran.vat_rate,
                lines[i].vat_code.rate
            )
            self.assertEqual(
                vat_tran.goods,
                lines[i].goods
            )
            self.assertEqual(
                vat_tran.vat,
                lines[i].vat
            )

        self.assertEqual(
            header.goods,
            sum( vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum( vat_tran.vat for vat_tran in vat_transactions)
        )
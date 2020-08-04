from datetime import datetime, timedelta
from itertools import chain

from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accountancy.testing.helpers import *
from cashbook.models import CashBook
from items.models import Item
from nominals.models import Nominal, NominalTransaction
from utils.helpers import sort_multiple
from vat.models import Vat

from ..helpers import (create_invoice_with_nom_entries, create_invoices,
                       create_lines, create_payments, create_credit_note_with_nom_entries)
from ..models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
MATCHING_FORM_PREFIX = "match"
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


def add_and_replace_objects(objects, replace_keys, extra_keys_and_values):
    for obj in objects:
        for old_key in replace_keys:
            new_key = replace_keys[old_key]
            same_value = obj[old_key]
            obj[new_key] = same_value
            del obj[old_key]
        for extra in extra_keys_and_values:
            extra_key = extra
            extra_value = extra_keys_and_values[extra_key]
            obj[extra_key] = extra_value
    return objects

def get_fields(obj, wanted_keys):
    d = {}
    for key in wanted_keys:
        d[key] = obj[key]
    return d


def to_dict(instance):
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    for f in opts.many_to_many:
        data[f.name] = [i.id for i in f.value_from_object(instance)]
    return data

def create_header(prefix, form):
    data = {}
    for field in form:
        data[prefix + "-" + field] = form[field]
    data[prefix + "-" + "period"] = PERIOD
    return data

def create_formset_data(prefix, forms):
    data = {}
    for i, form in enumerate(forms):
        for field in form:
            data[
                prefix + "-" + str(i) + "-" + field
            ] = form[field]
    if forms:
        i = i + 1 # pk keys start
    else:
        i = 0
    management_form = {
        prefix + "-TOTAL_FORMS": i,
        prefix + "-INITIAL_FORMS": 0,
        prefix + "-MIN_NUM_FORMS": 0,
        prefix + "-MAX_NUM_FORMS": 1000
    }
    data.update(management_form)
    return data


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




class CreateBroughtForwardInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create brought forward invoice view with t=bi GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pbi")
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi" selected>Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )

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


class CreateInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
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
        )
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
    

    # CORRECT USAGE
    # Can request create invoice view without GET parameters
    def test_get_request(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    # CORRECT USAGE
    # Can request create invoice view with t=i GET parameter
    def test_get_request_with_query_parameter(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 20)
        line_no = 1
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
                line.line_no,
                line_no
            )
            line_no = line_no + 1

    # CORRECT USAGE
    def test_entering_blank_lines(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 10
        line_forms += ([{
                'item': '',
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        line_no = 1
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
                line.line_no,
                line_no
            )
            line_no = line_no + 1




    # INCORRECT USAGE
    def test_invoice_header_is_invalid(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        

    # CORRECT USAGE
    def test_invoice_with_positive_input_is_saved_as_positive(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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

    # CORRECT USAGE
    def test_invoice_with_negative_input_is_saved_as_negative(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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


    """

    This section tests putting on a zero value transaction which can only be put on to match
    other transactions.

    """


    # CORRECT USAGE
    # THIS IS A ZERO VALUE HEADER TRANSACTION
    # WHICH IS THE WAY TO MATCH OTHER TRANSACTIONS
    # E.G. AN INVOICE AND CREDIT NOTE ON THE SUPPLIER ACCOUNT NEED MATCHING
    def test_header_total_is_zero_with_no_lines_and_matching_transactions_equal_zero(self):

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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
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
            '<li class="py-1">You are trying to match a total value of 20.'
            '  Because you are entering a zero value transaction the total amount to match must be zero also.</li>',
            html=True
        )


    # INCORRECT USUAGE
    def test_header_total_is_zero_with_no_lines_with_no_matching_transactions(self):

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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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


    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_less_than_total(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
            html=True
        )

    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
            html=True
        )

    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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

    # INCORRECT USAGE
    def test_header_total_is_non_zero_and_with_lines_which_do_not_total_entered_total(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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

    # CORRECT USAGE
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_less_than_total_NEGATIVE(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
			'<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
            html=True
        )


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
			'<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
            html=True
        )




    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total_NEGATIVE(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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

    # INCORRECT USAGE
    def test_header_total_is_non_zero_and_with_lines_which_do_not_total_entered_total_NEGATIVE(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
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


class CreateCreditNote(TestCase):

    """
    Remember we have to POST to /purchases/create?t=p
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")


    # CORRECT USAGE
    # Can request create payment view only with t=p GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pc")
        self.assertEqual(response.status_code, 200)
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
                '<option value="pi">Invoice</option>'
                '<option value="pc" selected>Credit Note</option>'
            '</select>',
            html=True
        )


class CreateBroughtForwardPayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create payment view only with t=bp GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pbp")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp" selected>Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class CreateBroughtForwardRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create payment view only with t=bp GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pbr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
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



# THIS WAS WRITTEN BACK WHEN PAYMENTS USED A DIFFERENT FORM TO INVOICES
# STILL KEEPS IT ANYWAY BUT NOT SO IMPORTANT NOW
class CreatePayment(TestCase):

    """
    Remember we have to POST to /purchases/create?t=p
    """

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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

        # Cash book
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.url = reverse("purchases:create")


    # CORRECT USAGE
    # Can request create payment view only with t=p GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pp")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp" selected>Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )

    # CORRECT USAGE
    def test_payment_with_positive_input_is_saved_as_negative(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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

    # CORRECT USAGE
    def test_payment_with_negative_input_is_saved_as_positive(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
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

    # CORRECT USAGE
    # THIS IS A ZERO VALUE HEADER TRANSACTION
    # WHICH IS THE WAY TO MATCH OTHER TRANSACTIONS
    # E.G. A PAYMENT AND A NEGATIVE PAYMENT NEED MATCHING
    def test_header_total_is_zero_and_matching_transactions_equal_zero(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "cash_book": self.cash_book.pk,   
                "type": "pp",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pp", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
    def test_header_total_is_zero_and_matching_transactions_do_not_equal_zero(self):
        
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "cash_book": self.cash_book.pk,   
                "type": "pp",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "pp", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        # SO FAR SAME AS TEST ABOVE.  NOW FOR THE DIFFERENCE.
        matching_forms[-1]["value"] = -80
        # Now the values to match do not equal 0 which is not acceptable
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
			'<li class="py-1">You are trying to match a total value of 20. '
            "Because you are entering a zero value transaction the total amount to match must be zero also.</li>",
            html=True
        )


    # INCORRECT USUAGE
    def test_header_total_is_zero_and_with_no_matching_transactions(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "cash_book": self.cash_book.pk,   
                "type": "pp",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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


    # CORRECT USAGE -- BUT THIS MEANS THE TOTAL OF THE LINES IS USED FOR THE HEADER
    # SO THIS IS NOT A ZERO VALUE MATCHING TRANSACTION
    def test_header_total_is_non_zero_and_no_matching_transactions_selected(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 100
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.total,
            -100
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

    # CORRECT USAGE
    def test_header_total_is_non_zero_and_with_matching_transactions_less_than_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "pay", 10, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        # by entering -100 we are creating a negative payment which has a positive balance
        # so we match the positive balance of 100.00
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            -2400
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
            -1000
        )
        self.assertEqual(
            header.due,
            header.total + 1000
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
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
    def test_header_total_is_non_zero_and_with_matching_transactions_equal_to_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 24, -100) # Negative payments of 2400 on account
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all().order_by("-pk")
        # this was seemingly ordering by primary key in ascending order but now does not.  So added order_by('-pk').
        self.assertEqual(len(headers), 25)
        header = headers[0]
        self.assertEqual(
            header.total,
            -2400
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
            -2400
        )
        self.assertEqual(
            header.due,
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
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
    def test_header_total_is_non_zero_and_with_matching_transactions_above_the_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 25, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
            html=True
        )


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_non_zero_and_with_matching_transactions_have_same_sign_as_new_header(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 100
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 100</li>',
            html=True
        )


    """
    As with the invoice tests we now test the non-zero total tests but this time entering negatives
    """


    # CORRECT USAGE -- BUT THIS MEANS THE TOTAL OF THE LINES IS USED FOR THE HEADER
    # SO THIS IS NOT A ZERO VALUE MATCHING TRANSACTION
    def test_header_total_is_non_zero_and_no_matching_transactions_selected_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -100
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
        response = self.client.post(self.url, data)
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

    # CORRECT USAGE
    def test_header_total_is_non_zero_and_with_matching_transactions_less_than_total_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "pay", 10, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        # by entering -100 we are creating a negative payment which has a positive balance
        # so we match the positive balance of 100.00
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            2400
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
            1000
        )
        self.assertEqual(
            header.due,
            header.total - 1000
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
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
    def test_header_total_is_non_zero_and_with_matching_transactions_equal_to_total_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 24, 100) # Negative payments of 2400 on account
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            2400
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
            2400
        )
        self.assertEqual(
            header.due,
            0
        )
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 0)
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
    def test_header_total_is_non_zero_and_with_matching_transactions_above_the_total_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 25, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
            html=True
        )


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_non_zero_and_with_matching_transactions_which_have_same_sign_as_new_header_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": -100
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -100</li>',
            html=True
        )



    """

    Same as with invoices tests

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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 2400
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -10})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Value must be between 0 and 100.00</li>',
            html=True
        )



    def test_illegal_matching_situation_2(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 100
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, -100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 130}) # rememeber the invoice we create above is not including VAT. So 120 total, not 100.00
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Value must be between 0 and 100.00</li>',
            html=True
        )


    def test_illegal_matching_situation_3(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -100
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, 100) # So -120.00 is the due
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 10})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(matching_data)
        data.update(line_data)
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
            '<li class="py-1">Value must be between 0 and -100.00</li>',
            html=True
        )


    def test_illegal_matching_situation_4(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -100
            }
        )
        data.update(header_data)
        headers_to_match_against = create_payments(self.supplier, "inv", 1, 100) # So -120.00 is the due
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -130}) # Trying to match -130.00 when due is only -120.00
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
            '<li class="py-1">Value must be between 0 and -100.00</li>',
            html=True
        )


# EditInvoice should be based on this
class EditPayment(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")

        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")

        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")

        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.bank_nominal)

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    """

    Let a payment be matched to multiple transaction types such that the payment is fully paid.

    The payment is therefore the matched_to transaction and the matched_by transactions are the others.

    """


    """
    First no new matching transactions are added
    """


    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="ref",
            date=timezone.now(),
            total=120,
            goods=100,
            vat=20
        )
        url = reverse("purchases:edit", kwargs={"pk": transaction.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp" selected>Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )

    # CORRECT USAGE
    # Payment total is increased.  Payment was previously fully matched
    def test_1(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 1000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 500}) # Same value as matched originally
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -2000)
        self.assertEqual(payment.due, -1000)
        self.assertEqual(payment.paid, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 700)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 700)
        self.assertEqual(invoices[1].paid, 500)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)  


    # INCORRECT USAGE
    # Payment total is decreased.  Payment was previously fully matched
    def test_2(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 1000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)        

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 500}) # Same value as matched originally
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(create_formset_data(LINE_FORM_PREFIX, []))
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 700)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 700)
        self.assertEqual(invoices[1].paid, 500)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 500</li>',
            html=True
        )


    # CORRECT USAGE
    # Payment total is increased
    # Match value of transaction increased
    # Payment still fully matched
    def test_3(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 1000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 1000}) # increase both matches by 500.00
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -2000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -2000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 200)
        self.assertEqual(invoices[0].paid, 1000)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 200)
        self.assertEqual(invoices[1].paid, 1000)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 1000)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 1000)  

    # CORRECT USAGE
    # Payment total is increased
    # Match value of transaction increased
    # Payment not fully matched now though
    def test_4(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 1000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 900}) # increase both matches by 400.00
        # This means the 2000.00 payment now has 1800.00 matched
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -2000)
        self.assertEqual(payment.due, -200)
        self.assertEqual(payment.paid, -1800)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 300)
        self.assertEqual(invoices[0].paid, 900)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 300)
        self.assertEqual(invoices[1].paid, 900)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 900)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 900)  


    # INCORRECT USAGE
    # Payment total is increased
    # Match value of transaction is increased which is ok per this matched header i.e. increase is below outstanding on this transaction
    # But now the matched value total is greater than the total value of the payment
    # 100.00 payment matched to two invoices 100.00 and 50.00.  (Only 50.00 of first invoice is matched to payment)
    # So -100 = 50 + 50 means the payment is fully matched
    # Now increase payment to -110
    # And match first invoice up to 100
    # So now we have 100 + 50 = 150 which is greater than the 110 payment total
    def test_5(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 2000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 1900)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 2400)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 1900)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 1500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 1500})
        # So we are trying to match a 1500 payment to 3000 worth of invoices
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(create_formset_data(LINE_FORM_PREFIX, []))
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -1000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 2400)
        self.assertEqual(invoices[0].due, 1900)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 2400)
        self.assertEqual(invoices[1].due, 1900)
        self.assertEqual(invoices[1].paid, 500)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)  

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1500</li>',
            html=True
        )


    # CORRECT USAGE 
    # Payment total is decreased
    # Match value of a transaction is decreased
    # Payment still fully paid
    def test_6(self):
        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 2000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 1900)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 2400)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 1900)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 250})
        # So we are trying to match a 1500 payment to 3000 worth of invoices
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -500)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -500)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 2400)
        self.assertEqual(invoices[0].due, 2150)
        self.assertEqual(invoices[0].paid, 250)
        self.assertEqual(invoices[1].total, 2400)
        self.assertEqual(invoices[1].due, 2150)
        self.assertEqual(invoices[1].paid, 250)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 250)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 250)  


    # CORRECT USAGE
    # Payment total is decreased
    # Match value is decreased
    # Yet payment is not fully paid now
    def test_7(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 2, 2000)
        match(payment, [ ( invoice, 500 ) for invoice in invoices ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 1900)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 2400)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 1900)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment0",
                "date": payment.date,
                "total": 500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 200})
        # So we are trying to match a 1500 payment to 3000 worth of invoices
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -500)
        self.assertEqual(payment.due, -100)
        self.assertEqual(payment.paid, -400)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 2400)
        self.assertEqual(invoices[0].due, 2200)
        self.assertEqual(invoices[0].paid, 200)
        self.assertEqual(invoices[1].total, 2400)
        self.assertEqual(invoices[1].due, 2200)
        self.assertEqual(invoices[1].paid, 200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 200)  


    # INCORRECT USAGE
    # Payment total is decreased
    # Match value of transaction is decreased so is ok on the header
    # But now the match value total is not valid
    # Example.  100 payment is matched to a 200 payment and a 300 invoice.
    # The payment is reduced to 80.  And only 150.00 of the payment is now matched
    # This isn't allowed as obviously a 80 + 150 payment cannot pay a 300 invoice
    def test_8(self):

        # IN FACT WE WILL JUST MATCH A PAYMENT TO A POSITIVE AND NEGATIVE INVOICE

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 2000)
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        match(payment, [ ( invoices[0], 2000 ), ( invoices[1], -1000) ])

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 2000)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1000)
        self.assertEqual(headers[2].due, -200)

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 2000)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, -1000)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 800
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([invoices_to_match_against[0]], {"id": "matched_to"}, {"value": 2000})
        matching_forms += add_and_replace_objects([invoices_to_match_against[1]], {"id": "matched_to"}, {"value": -900})
        # So we are trying to match a 1500 payment to 3000 worth of invoices
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(create_formset_data(LINE_FORM_PREFIX, []))
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -1000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].total, 2400)
        self.assertEqual(invoices[0].due, 400)
        self.assertEqual(invoices[0].paid, 2000)
        self.assertEqual(invoices[1].total, -1200)
        self.assertEqual(invoices[1].due, -200)
        self.assertEqual(invoices[1].paid, -1000)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 2000)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, -1000)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 800</li>',
            html=True
        )

    """
    Now we repeat tests 3 to 8 but this time try the same thing but by adding new transactions
    """

    # test_3 again but this time we also create a new matching record
    # i.e. match a new transaction to the matched_by transaction
    # CORRECT USAGE
    # Payment total is increased
    # Match value of transaction increased
    # Payment still fully matched
    def test_9(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 3, 1000)
        invoices_to_match = list(invoices)[:2]
        invoice_not_matched = list(invoices)[-1]
        match(payment, [ ( invoice, 500 ) for invoice in invoices_to_match ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)
        # and now the invoice not matched
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, 1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, 1200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda h : h.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 500})
        matching_forms[-1]["value"] = 1000
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # This means we haven't changed the original two invoices matched against the payment - both still match only 500.00
        # But we've matched the third invoice to the payment also and for a value of 1000.00
        # So the payment should be fully paid now
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -2000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -2000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 700)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 700)
        self.assertEqual(invoices[1].paid, 500)
        self.assertEqual(invoices[2].total, 1200)
        self.assertEqual(invoices[2].due, 200)
        self.assertEqual(invoices[2].paid, 1000)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)  
        self.assertEqual(matches[2].matched_by, payment)
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, 1000)  

    # test_4 again but this time we also create a new matching record
    # i.e. match a new transaction to the matched_by transaction
    # CORRECT USAGE
    # Payment total is increased
    # Match value of transaction increased
    # Payment not fully matched now though
    def test_10(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 3, 1000)
        invoices_to_match = list(invoices)[:2]
        invoice_not_matched = list(invoices)[-1]
        match(payment, [ ( invoice, 500 ) for invoice in invoices_to_match ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)
        # and now the invoice not matched
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, 1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, 1200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda h : h.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 500})
        matching_forms[-1]["value"] = 600
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # This means we haven't changed the original two invoices matched against the payment - both still match only 500.00
        # But we've matched the third invoice to the payment also and for a value of 1000.00
        # So the payment should be fully paid now
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -2000)
        self.assertEqual(payment.due, -400)
        self.assertEqual(payment.paid, -1600)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 700)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 700)
        self.assertEqual(invoices[1].paid, 500)
        self.assertEqual(invoices[2].total, 1200)
        self.assertEqual(invoices[2].due, 600)
        self.assertEqual(invoices[2].paid, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)  
        self.assertEqual(matches[2].matched_by, payment)
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, 600)  

    # test_5 again but this time including a new transaction to match
    # INCORRECT USAGE
    # Payment total is increased
    # Match value of transaction is increased which is ok per this matched header i.e. increase is below outstanding on this transaction
    # But now the matched value total is greater than the total value of the payment
    # 100.00 payment matched to two invoices 100.00 and 50.00.  (Only 50.00 of first invoice is matched to payment)
    # So -100 = 50 + 50 means the payment is fully matched
    # Now increase payment to -110
    # And match first invoice up to 100
    # So now we have 100 + 50 = 150 which is greater than the 110 payment total
    def test_11(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 3, 1000)
        invoices_to_match = list(invoices)[:2]
        invoice_not_matched = list(invoices)[-1]
        match(payment, [ ( invoice, 500 ) for invoice in invoices_to_match ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)
        # and now the invoice not matched
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, 1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, 1200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda h : h.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 2000
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 1000})
        matching_forms[-1]["value"] = 1000
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # So we are trying to match 3 x 1000.00 invoices fully to a 2000.00 payment
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(create_formset_data(LINE_FORM_PREFIX, []))
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -1000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 700)
        self.assertEqual(invoices[0].paid, 500)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 700)
        self.assertEqual(invoices[1].paid, 500)
        self.assertEqual(invoices[2].total, 1200)
        self.assertEqual(invoices[2].due, 1200)
        self.assertEqual(invoices[2].paid, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)  

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2000</li>',
            html=True
        )


    # test_6 again but this time including a new transaction to match
    # CORRECT USAGE 
    # Payment total is decreased
    # Match value of a transaction is decreased
    # Payment still fully paid
    def test_12(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 3, 1000)
        invoices_to_match = list(invoices)[:2]
        invoice_not_matched = list(invoices)[-1]
        match(payment, [ ( invoice, 500 ) for invoice in invoices_to_match ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)
        # and now the invoice not matched
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, 1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, 1200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda h : h.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 200})
        matching_forms[-1]["value"] = 100
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # So we are trying to match 3 x 1000.00 invoices fully to a 2000.00 payment
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -500)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -500)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 1000)
        self.assertEqual(invoices[0].paid, 200)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 1000)
        self.assertEqual(invoices[1].paid, 200)
        self.assertEqual(invoices[2].total, 1200)
        self.assertEqual(invoices[2].due, 1100)
        self.assertEqual(invoices[2].paid, 100)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 200)
        self.assertEqual(matches[2].matched_by, payment)
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, 100)

    # test_7 again but this time including a new transaction to match
    # CORRECT USAGE
    # Payment total is decreased
    # Match value is decreased
    # Yet payment is not fully paid now
    def test_13(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = create_invoices(self.supplier, "invoice", 3, 1000)
        invoices_to_match = list(invoices)[:2]
        invoice_not_matched = list(invoices)[-1]
        match(payment, [ ( invoice, 500 ) for invoice in invoices_to_match ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 500)
        self.assertEqual(headers[1].due, 700)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 500)
        self.assertEqual(headers[2].due, 700)
        # and now the invoice not matched
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, 1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, 1200)


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 500)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 500)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda h : h.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 500
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(invoices_to_match_against, {"id": "matched_to"}, {"value": 200})
        matching_forms[-1]["value"] = 50
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        # So we are trying to match 3 x 1000.00 invoices fully to a 2000.00 payment
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -500)
        self.assertEqual(payment.due, -50)
        self.assertEqual(payment.paid, -450)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 1200)
        self.assertEqual(invoices[0].due, 1000)
        self.assertEqual(invoices[0].paid, 200)
        self.assertEqual(invoices[1].total, 1200)
        self.assertEqual(invoices[1].due, 1000)
        self.assertEqual(invoices[1].paid, 200)
        self.assertEqual(invoices[2].total, 1200)
        self.assertEqual(invoices[2].due, 1150)
        self.assertEqual(invoices[2].paid, 50)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, 200)
        self.assertEqual(matches[2].matched_by, payment)
        self.assertEqual(matches[2].matched_to, invoices[2])
        self.assertEqual(matches[2].value, 50)

    # test_8 but with new transactions
    # INCORRECT USAGE
    # Payment total is decreased
    # Match value of transaction is decreased so is ok on the header
    # But now the match value total is not valid
    # Example.  100 payment is matched to a 200 payment and a 300 invoice.
    # The payment is reduced to 80.  And only 150.00 of the payment is now matched
    # This isn't allowed as obviously a 80 + 150 payment cannot pay a 300 invoice
    def test_14(self):

        # IN FACT WE WILL JUST MATCH A PAYMENT TO A POSITIVE AND NEGATIVE INVOICE

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 2000)
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices += create_invoices(self.supplier, "invoice", 1, -1000)
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        match(payment, [ ( invoices[0], 2000 ), ( invoices[1], -1000) ])

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 4)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -1000)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 2400)
        self.assertEqual(headers[1].paid, 2000)
        self.assertEqual(headers[1].due, 400)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, -1200)
        self.assertEqual(headers[2].paid, -1000)
        self.assertEqual(headers[2].due, -200)
        self.assertEqual(headers[3].pk, invoices[2].pk)
        self.assertEqual(headers[3].total, -1200)
        self.assertEqual(headers[3].paid, 0)
        self.assertEqual(headers[3].due, -1200)


        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 2000)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, -1000)

        payment.refresh_from_db()
        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])

        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": "payment",
                "date": payment.date,
                "total": 800
            }
        )
        data.update(header_data)
        invoices_to_match_against_orig = invoices
        invoices_as_dicts = [ to_dict(invoice) for invoice in invoices ]
        invoices_to_match_against = [ get_fields(invoice, ['type', 'ref', 'total', 'paid', 'due', 'id']) for invoice in invoices_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([invoices_to_match_against[0]], {"id": "matched_to"}, {"value": 1000})
        matching_forms += add_and_replace_objects([invoices_to_match_against[1]], {"id": "matched_to"}, {"value": -900})
        matching_forms += add_and_replace_objects([invoices_to_match_against[2]], {"id": "matched_to"}, {"value": -900})
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2
        data.update(create_formset_data(LINE_FORM_PREFIX, []))
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        payment = PurchaseHeader.objects.get(pk=payment.pk)
        self.assertEqual(payment.total, -1000)
        self.assertEqual(payment.due, 0)
        self.assertEqual(payment.paid, -1000)

        invoices = PurchaseHeader.objects.filter(type="pi")
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices[0].total, 2400)
        self.assertEqual(invoices[0].due, 400)
        self.assertEqual(invoices[0].paid, 2000)
        self.assertEqual(invoices[1].total, -1200)
        self.assertEqual(invoices[1].due, -200)
        self.assertEqual(invoices[1].paid, -1000)
        self.assertEqual(invoices[2].total, -1200)
        self.assertEqual(invoices[2].due, -1200)
        self.assertEqual(invoices[2].paid, 0)


        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 2000)
        self.assertEqual(matches[1].matched_by, payment)
        self.assertEqual(matches[1].matched_to, invoices[1])
        self.assertEqual(matches[1].value, -1000)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 800</li>',
            html=True
        )


    """
    Finally we need to just check that the matched value cannot exceed the due amount of the transaction
    or fall below zero (or above zero) depending on whether is a debit or a credit.... THIS HAS BEEN CHECKED ALREADY THOUGH, I THINK
    """


    """
    So far we have tested only editing payments where the matching records have
    this same payment as matched_by.  Now we test editing the matching for
    a payment where it has a matched transaction where the payment is the matched_to
    in the relationship.

    I did this for EditInvoice first so these tests are based on the others.
    """

    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    def test_15(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 1000
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 800
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
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
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 800)
        self.assertEqual(headers[2].due, 400)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -800) 


    # CORRECT USAGE
    # WE DECREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    def test_16(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 1000
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 0
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -200)
        self.assertEqual(headers[0].due, -800)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 0)
        self.assertEqual(headers[2].due, 1200)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)


    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # ALSO INCREASE THE HEADER
    def test_17(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 1400
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 1200
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1400)
        self.assertEqual(headers[0].paid, -1400)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 1200)
        self.assertEqual(headers[2].due, 0)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -1200) 


    # CORRECT USAGE
    # WE INCREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # AND DECREASE THE HEADER
    def test_18(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 900
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 700
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -900)
        self.assertEqual(headers[0].paid, -900)
        self.assertEqual(headers[0].due, 0)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 700)
        self.assertEqual(headers[2].due, 500)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -700) 


    # CORRECT USAGE
    # WE DECREASE THE MATCH VALUE OF THE MATCH TRANSACTION WHERE THE HEADER BEING EDITED
    # IS THE MATCHED_TO HEADER
    # AND DECREASE THE HEADER
    def test_19(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 900
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 400
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -900)
        self.assertEqual(headers[0].paid, -600)
        self.assertEqual(headers[0].due, -300)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 400)
        self.assertEqual(headers[2].due, 800)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -400) 


    # INCORRECT USAGE
    # Same as test_33 but we just try and match a value wrongly - incorrect sign
    def test_20(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 900
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = -400
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Value must be between 0 and 1200.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # match is ok at match record level when taken in isolation
    # but incorrect overall
    def test_21(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 900
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 1000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 900</li>',
            html=True
        )


    # NOW I CHECK AN INVALID HEADER, INVALID LINES AND INVALID MATCHING
    # AGAIN JUST USE TEST_33 AS A BASE

    # INCORRECT USAGE
    # INVALID HEADER
    def test_22(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": 99999999,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 900
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 400
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600) 

        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )


    # INCORRECT USAGE
    # INVALID MATCHING
    def test_23(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 2, 1000)
        # SECOND INVOICE
        invoices = sort_multiple(invoices, *[ (lambda i : i.pk, False) ])
        match_by, match_to = match(payment, [ (invoices[0], 200) ] ) # FIRST MATCH
        payment = match_by
        match_by, match_to = match(invoices[1], [ (payment, -600) ]) # SECOND MATCH

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600)   
    
        url = reverse("purchases:edit", kwargs={"pk": payment.pk})

        # CHANGES
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": headers[0].ref,
                "date": headers[0].date,
                "total": 1000
            }
        )
        data.update(header_data)
        matching_trans = [ invoices[0], invoices[1] ]
        matching_trans_as_dicts = [ to_dict(m) for m in matching_trans ]
        matching_trans = [ get_fields(m, ['type', 'ref', 'total', 'paid', 'due', 'id']) for m in matching_trans_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([matching_trans[0]], {"id": "matched_to"}, {"value": 200}) # THIS IS LIKE ALL THE OTHER TESTS
        matching_forms[0]["id"] = matches[0].pk
        # THIS IS THE DIFFERENCE
        matching_trans[1]["id"] = matches[1].pk
        matching_trans[1]["matched_to"] = payment.pk # THIS IS NOT NEEDED FOR VALIDATION LOGIC BUT IS A REQUIRED FIELD
        matching_trans[1]["value"] = 1000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0].pk, payment.pk)
        self.assertEqual(headers[0].total, -1000)
        self.assertEqual(headers[0].paid, -800)
        self.assertEqual(headers[0].due, -200)
        self.assertEqual(headers[1].pk, invoices[0].pk)
        self.assertEqual(headers[1].total, 1200)
        self.assertEqual(headers[1].paid, 200)
        self.assertEqual(headers[1].due, 1000)
        self.assertEqual(headers[2].pk, invoices[1].pk)
        self.assertEqual(headers[2].total, 1200)
        self.assertEqual(headers[2].paid, 600)
        self.assertEqual(headers[2].due, 600)

        matches = PurchaseMatching.objects.all()
        matches = sort_multiple(matches, *[ (lambda m : m.pk, False) ])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_by, payment)
        self.assertEqual(matches[0].matched_to, invoices[0])
        self.assertEqual(matches[0].value, 200)
        self.assertEqual(matches[1].matched_by, invoices[1])
        self.assertEqual(matches[1].matched_to, payment)
        self.assertEqual(matches[1].value, -600) 

        self.assertContains(
            response,
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 1000</li>',
            html=True
        )


class CreateRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    # Can request create refund view only with t=bp GET parameter
    def test_get_request_with_query_parameter(self):
        response = self.client.get(self.url + "?t=pr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr" selected>Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class EditBroughtForwardInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pbi",
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
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi" selected>Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class EditBroughtForwardCreditNote(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pbc",
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



class EditInvoice(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.item = Item.objects.create(code="aa", description="aa-aa")
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

    """

    Let a payment be matched to multiple transaction types such that the payment is fully paid.

    The payment is therefore the matched_to transaction and the matched_by transactions are the others.

    """


    """
    First no new matching transactions are added
    """


    # CORRECT USAGE
    # add a new matching transaction for 0 value
    # edit an existing to zero value
    def test_match_value_of_zero_is_removed_where_edit_tran_is_matched_by_for_all_match_records(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = 0 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
    # Invoice total is increased (the invoice this time is the matched_to transaction)
    # Lines are added to match the header total
    # Payment was previously fully matched
    def test_line_no_changed(self):
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])

        lines_as_dicts = [ to_dict(line) for line in lines ]
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        self.assertEqual(lines[8].pk, lines_orig[-1].pk)
        self.assertEqual(lines[8].item, self.item)
        self.assertEqual(lines[8].description, self.description)
        self.assertEqual(lines[8].goods, 100)
        self.assertEqual(lines[8].nominal, self.nominal)
        self.assertEqual(lines[8].vat_code, self.vat_code)
        self.assertEqual(lines[8].vat, 20)
        self.assertEqual(lines[8].line_no, 9)

        self.assertEqual(lines[9].pk, lines_orig[-2].pk)
        self.assertEqual(lines[9].item, self.item)
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
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])


        lines_as_dicts = [ to_dict(line) for line in lines ]
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(line.line_no, line_no)
            line_no = line_no + 1

        self.assertEqual(lines[8].pk, lines_orig[-1].pk)
        self.assertEqual(lines[8].item, self.item)
        self.assertEqual(lines[8].description, self.description)
        self.assertEqual(lines[8].goods, 100)
        self.assertEqual(lines[8].nominal, self.nominal)
        self.assertEqual(lines[8].vat_code, self.vat_code)
        self.assertEqual(lines[8].vat, 20)
        self.assertEqual(lines[8].line_no, 9)

    # CORRECT USAGE
    # Invoice total is increased (the invoice this time is the matched_to transaction)
    # Lines are added to match the header total
    # Payment was previously fully matched
    def test_1(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1080</li>',
            html=True
        )


    # INCORRECT USAGE
    # Same as above but this time we lower the line value rather than delete a line
    def test_4(self):
        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_trans[-1]["goods"] = 0
        line_trans[-1]["vat"] = 0
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1080</li>',
            html=True
        )



    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is still fully matched
    def test_5(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[1]["value"] = -600
        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2100</li>',
            html=True
        )

    # INCORRECT USAGE
    # Same test as above except we increase the invoice by increasing an existing line value this time
    def test_10(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1320</li>',
            html=True
        )


    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_11(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[-1]["value"] = -480

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[-1]["value"] = -540

        # Remember we changing EXISTING instances so we need to post the id of the instance also
        matching_forms[0]["id"] = matches[0].pk
        matching_forms[1]["id"] = matches[1].pk
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1080</li>',
            html=True
        )


    # INCORRECT USAGE
    # Decrease line value so the total decreases
    # Matching is not right though
    def test_16(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1140</li>',
            html=True
        )


    # Same as test_5 but this time we match a new transaction
    # CORRECT USAGE
    # Invoice total is increased by adding new lines
    # Match value of transaction is increased
    # Invoice is still fully matched
    def test_17(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]

        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        for line in lines[10:]:
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -80}
        )

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[1]["value"] = -600
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[0]["value"] = -1000
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        new_lines = [ # whereas new here so no ID
                {
                    'item': self.item.pk,
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2100</li>',
            html=True
        )


    # test_10 again but this time creating a new transaction
    # INCORRECT USAGE
    # Same test as above except we increase the invoice by increasing an existing line value this time
    def test_22(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ] # here we are posting the ID for the lines which already exist
        lines_as_dicts = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1320</li>',
            html=True
        )


    # test_11 again but this time creating a new matching transaction
    # CORRECT USAGE
    # Delete a line so the total decreases - like test_3
    # But this time we lower the matching also so invoice is still fully paid
    def test_23(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[-1]["value"] = -400
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_forms[-1]["value"] = -500
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -100}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            line_no = line_no + 1

        line = lines[-1]
        self.assertEqual(line.line_no, line_no)
        self.assertEqual(line.item, self.item)
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

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1080</li>',
            html=True
        )

    # test_16 again but this time we create a new matching transaction
    # INCORRECT USAGE
    # Decrease line value so the total decreases
    # Matching is not right though
    def test_28(self):

        # SET UP
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        # These are the existing matches increased
        # Now add the new
        matching_forms += add_and_replace_objects( 
            [ 
                get_fields(to_dict(invoices[2]), ['type', 'ref', 'total', 'paid', 'due', 'id']) 
            ], 
            {"id": "matched_to"}, 
            {"value": -200}
        )
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1140</li>',
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -800 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -100 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -1000 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -940 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -100 # USER WANTS TO ENTER A NEGATIVE HERE EVEN THOUGH WILL BE SAVED AS POSITIVE
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)

        line = lines[-1]
        self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = 100 # THIS IS WRONG.  SHOULD BE A NEGATIVE.
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2 

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Value must be between 0 and -1000.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # Same as above two tests but this time we do incorrect matching overall i.e. match is ok at match record level when taken in isolation
    def test_35(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -1000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # SO TRYING TO MATCH -1200 to a 1140 invoice which is wrong

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1140</li>',
            html=True
        )

    # NOW I CHECK AN INVALID HEADER, INVALID LINES AND INVALID MATCHING
    # AGAIN JUST USE TEST_33 AS A BASE

    # INCORRECT USAGE
    # INVALID HEADER
    def test_36(self):

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -600
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -600
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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

        # create the payment
        payment = create_payments(self.supplier, 'payment', 1, value=1000)[0]
        # create the invoice - THIS IS WHAT WE ARE EDITING
        invoices = []
        invoices += create_invoices(self.supplier, "invoice", 1, 1000)
        lines = create_lines(
            invoices[0], 
            [
                {
                    'item': self.item,
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
            self.assertEqual(line.item, self.item)
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
        matching_trans[1]["value"] = -2000
        matching_forms.append(matching_trans[1])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 2

        # HEADER IS INVALID
        # LINE IS VALID
        # MATCHING IS VALID

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
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
            self.assertEqual(line.item, self.item)
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
            '<li class="py-1">Value must be between 0 and -1000.00</li>',
            html=True
        )

class EditCreditNote(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pc",
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
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc" selected>Credit Note</option>'
            '</select>',
            html=True
        )


class EditBroughtForwardPayment(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pbp",
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
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp" selected>Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr">Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )


class EditBroughtForwardRefund(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pbr",
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
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
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


# EDITPAYMENT IS ABOVE

class EditRefund(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    def test_get_request(self):
        transaction = PurchaseHeader.objects.create(
            type="pr",
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
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
                '<option value="">---------</option>'
                '<option value="pbi">Brought Forward Invoice</option>'
                '<option value="pbc">Brought Forward Credit Note</option>'
                '<option value="pbp">Brought Forward Payment</option>'
                '<option value="pbr">Brought Forward Refund</option>'
                '<option value="pp">Payment</option>'
                '<option value="pr" selected>Refund</option>'
                '<option value="pi">Invoice</option>'
                '<option value="pc">Credit Note</option>'
            '</select>',
            html=True
        )




class GeneralTransactionTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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
    def test_approve_and_another_redirection(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        data.update({
            'approve': 'add_another'
        })
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.request["PATH_INFO"],
            "/purchases/create"
        )


    # CORRECT USAGE
    def test_add_redirection(self):
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
                'description': self.description,
                'goods': 100,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
            }]) * 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(matching_data)
        data.update(line_data)
        data.update({
            'approve': 'do_not_add_another'
        })
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.request["PATH_INFO"],
            "/purchases/transactions"
        )




"""

Test that nominal entries are created correctly

"""


class CreateInvoiceNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
                line.item,
                self.item
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        # assuming the lines are created in the same order
        # as the nominal entries....

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


    # CORRECT USAGE
    # Each line has a goods value above zero
    # And the vat is a zero value
    # We are only testing here that no nominal transactions for zero are created
    # We are not concerned about the vat return at all
    def test_nominals_created_for_lines_with_goods_and_vat_equal_to_zero(self):

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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20
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


    # CORRECT USAGE
    # VAT only invoice
    # I.e. goods = 0 and vat = 20 on each analysis line
    def test_vat_only_lines_invoice(self):

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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        line_forms = ([{
                'item': self.item.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20
            # i.e. 0 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entry for each goods + vat value
        )
        # assuming the lines are created in the same order
        # as the nominal entries....
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


    # CORRECT USAGE
    # Zero value invoice
    # So analysis must cancel out
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_analysis(self):

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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
                'description': self.description,
                'goods': 20,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 10
        line_forms += (
            [{
                'item': self.item.pk,
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines_orig = lines
        lines = lines_orig[:10]
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
        lines = lines_orig[10:]
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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


class CreateCreditNoteNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pc",
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
                'item': self.item.pk,
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
        lines = PurchaseLine.objects.all()
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
            # i.e. 20 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entries for each goods + vat value
        )
        # assuming the lines are created in the same order
        # as the nominal entries....

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
                120
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


    # CORRECT USAGE
    # Each line has a goods value above zero
    # And the vat is a zero value
    # We are only testing here that no nominal transactions for zero are created
    # We are not concerned about the vat return at all
    def test_nominals_created_for_lines_with_goods_and_vat_equal_to_zero(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pc",
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
                'item': self.item.pk,
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
            -20 * (100 + 0)
        )
        self.assertEqual(
            header.goods,
            -20 * 100
        )
        self.assertEqual(
            header.vat,
            -20 * 0
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
                line.item,
                self.item
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
                0
            )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20
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
                't'
            )


        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )


    # CORRECT USAGE
    # VAT only invoice
    # I.e. goods = 0 and vat = 20 on each analysis line
    def test_vat_only_lines_invoice(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pc",
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
                'item': self.item.pk,
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
            -20 * (0 + 20)
        )
        self.assertEqual(
            header.goods,
            0 * 100
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
        lines = PurchaseLine.objects.all()
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
                -20
            )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            20 + 20
            # i.e. 0 nominal entries for each goods value
            # 20 nominal entries for each vat value
            # 20 nominal entry for each goods + vat value
        )
        # assuming the lines are created in the same order
        # as the nominal entries....
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
                't'
            )


        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )


    # CORRECT USAGE
    # Zero value credit note
    # So analysis must cancel out
    # A zero value transaction is only permissable if we are matching -- a good check in the system
    def test_zero_invoice_with_analysis(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pc",
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_forms = ([{
                'item': self.item.pk,
                'description': self.description,
                'goods': 20,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': -20
            }]) * 10
        line_forms += (
            [{
                'item': self.item.pk,
                'description': self.description,
                'goods': -20,
                'nominal': self.nominal.pk,
                'vat_code': self.vat_code.pk,
                'vat': 20
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines_orig = lines
        lines = lines_orig[:10]
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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
        lines = lines_orig[10:]
        for line in lines:
            self.assertEqual(
                line.item,
                self.item
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

        total = 0
        for tran in nom_trans:
            total = total + tran.value
        self.assertEqual(
            total,
            0
        )



class CreateBroughtForwardInvoiceNominalTransactions(TestCase):

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
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')
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
                "type": "pbi",
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
            'pbi'
        )
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
                line.item,
                None
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
                None
            )
            self.assertEqual(
                line.vat_code,
                None
            )
            self.assertEqual(
                line.vat,
                20
            )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(len(nom_trans), 0)



class CreatePaymentNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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


    # CORRECT USAGE
    # A payment with no matching
    def test_non_zero_payment(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
            # 1 is the bank nominal
            # 1 is the control account
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
        self.assertEqual(
            tran.module,
            PL_MODULE
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
            self.purchase_control # bank nominal
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


    # CORRECT USAGE
    # A payment with no matching
    def test_zero_payment(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "pp",
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        data.update(matching_data)
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
            headers[1]
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
            headers[2]
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


class EditInvoiceNominalEntries(TestCase):

    """
    Based on same tests as CreateInvoiceNominalEntries
    """

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            self.assertEqual(line.item, self.item)
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
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 50
        line_forms[-1]["vat"] = 10
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
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

    # CORRECT USAGE
    # Based on above
    # Except this time we reduce goods to zero on a line
    # This should delete the corresponding nominal transaction for goods
    # And obviously change the control account nominal value
    def test_goods_reduced_to_zero_but_vat_non_zero_on_a_line(self):

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            self.assertEqual(line.item, self.item)
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
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 20
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
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


    # CORRECT USAGE
    # Same as above except we now blank out vat and not goods
    def test_vat_reduced_to_zero_but_goods_non_zero_on_a_line(self):

        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            self.assertEqual(line.item, self.item)
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
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 100
        line_forms[-1]["vat"] = 0
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
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


    # CORRECT USAGE
    # We expect the line and the three nominal transactions to all be deleted
    def test_goods_and_vat_for_line_reduced_to_zero(self):
 
        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            self.assertEqual(line.item, self.item)
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
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 0
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            19
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
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


    def test_line_marked_as_deleted_has_line_and_nominals_removed(self):
 
        create_invoice_with_nom_entries(
            {
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            self.assertEqual(line.item, self.item)
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
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 100
        line_forms[-1]["vat"] = 20
        line_forms[-1]["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            19
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
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



class EditCreditNoteNominalEntries(TestCase):

    """
    Based on same tests as EditInvoiceNominalEntries
    """

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.item = Item.objects.create(code="aa", description="aa-aa")
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

        create_credit_note_with_nom_entries(
            {
                "type": "pc",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                120
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
                "total": (-1 * header.total - 60) # we half the goods and vat for a line
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = -50
        line_forms[-1]["vat"] = -10
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, -50)
        self.assertEqual(edited_line.nominal, self.nominal)
        self.assertEqual(edited_line.vat_code, self.vat_code)
        self.assertEqual(edited_line.vat, -10)
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

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        unedited_goods_nom_trans = goods_nom_trans[:-1]

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                1 * 120
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
            -50
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
            -10
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
            60
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

    # CORRECT USAGE
    # Based on above
    # Except this time we reduce goods to zero on a line
    # This should delete the corresponding nominal transaction for goods
    # And obviously change the control account nominal value
    def test_goods_reduced_to_zero_but_vat_non_zero_on_a_line(self):

        create_credit_note_with_nom_entries(
            {
                "type": "pc",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                120
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
                "total": (-1 * header.total) - 100 # we set goods = 0 when previously was 100
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = -20
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)


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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            19 + 20 + 20
            # 19 goods nominal transactions
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, 0)
        self.assertEqual(edited_line.nominal, self.nominal)
        self.assertEqual(edited_line.vat_code, self.vat_code)
        self.assertEqual(edited_line.vat, -20)
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

        goods_nom_trans = nom_trans[:-2:3]
        vat_nom_trans = nom_trans[1:-2:3]
        total_nom_trans = nom_trans[2:-2:3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                1 * 120
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
            -20
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
            20
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


    # CORRECT USAGE
    # Same as above except we now blank out vat and not goods
    def test_vat_reduced_to_zero_but_goods_non_zero_on_a_line(self):

        create_credit_note_with_nom_entries(
            {
                "type": "pc",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                120
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
                "total": (-1 * header.total) - 20 # we set vat = 0 when previously was 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = -100
        line_forms[-1]["vat"] = 0
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            20 + 19 + 20
            # 19 goods nominal transactions
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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

        edited_line = lines[-1]
        self.assertEqual(edited_line.header, header)
        self.assertEqual(edited_line.item, self.item)
        self.assertEqual(edited_line.description, self.description)
        self.assertEqual(edited_line.goods, -100)
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

        goods_nom_trans = nom_trans[:-2:3]
        vat_nom_trans = nom_trans[1:-2:3]
        total_nom_trans = nom_trans[2:-2:3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                1 * 120
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
            -100
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
            100
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


    # CORRECT USAGE
    # We expect the line and the three nominal transactions to all be deleted
    def test_goods_and_vat_for_line_reduced_to_zero(self):
 
        create_credit_note_with_nom_entries(
            {
                "type": "pc",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                120
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
                "total": (-1 * header.total) - 120 # we set vat = 0 when previously was 20
            }
        )

        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_forms[-1]["goods"] = 0
        line_forms[-1]["vat"] = 0
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            19 + 19 + 19
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            19
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                1 * 120
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


    def test_line_marked_as_deleted_has_line_and_nominals_removed(self):
 
        create_credit_note_with_nom_entries(
            {
                "type": "pc",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            [
                {
                    'item': self.item,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

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
            20 + 20 + 20
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for i, tran in enumerate(goods_nom_trans):
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                120
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
                "total": (-1 * header.total) - 120 # we set vat = 0 when previously was 20
            }
        )
        data.update(header_data)

        lines_as_dicts = [ to_dict(line) for line in lines ]
        line_trans = [ get_fields(line, ['id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']) for line in lines_as_dicts ]
        line_forms = line_trans
        line_forms[-1]["goods"] = 100
        line_forms[-1]["vat"] = 20
        for form in line_forms:
            form["goods"] *= -1
            form["vat"] *= -1
        line_forms[-1]["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
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
        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])
        self.assertEqual(
            len(nom_trans),
            19 + 19 + 19
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            19
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])
        lines = list(lines)

        unedited_lines = list(lines)[:-1]

        for i, line in enumerate(unedited_lines):
            self.assertEqual(line.header, header)
            self.assertEqual(line.item, self.item)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, -100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, -20)
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


        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        unedited_goods_nom_trans = goods_nom_trans

        # CHECK OUR UNEDITED FIRST ARE INDEED UNEDITED

        for tran in unedited_goods_nom_trans:
            self.assertEqual(
                tran.value,
                -100
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
                -20
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
                1 * 120
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
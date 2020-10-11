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
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": -100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": 100})
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
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": -100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": 100})
        # SO FAR SAME AS TEST ABOVE.  NOW FOR THE DIFFERENCE.
        matching_forms[-1]["value"] = 80
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
			'<li class="py-1">You are trying to match a total value of 20.00. '
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
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -100})
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -100.00</li>',
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
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 100})
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 100.00</li>',
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
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 10})
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
            '<li class="py-1">Value must be between 0 and -100.00</li>',
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
        headers_to_match_against = create_payments(self.supplier, "inv", 1, 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": -10})
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
            '<li class="py-1">Value must be between 0 and 100.00</li>',
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
            '<li class="py-1">Value must be between 0 and 100.00</li>',
            html=True
        )


    # INCORRECT USAGE
    # Check header is invalid with matching
    def test_header_invalid_with_matching(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,   
                "type": "pp",
                "supplier": 99999999999999,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        data.update(header_data)
        headers_to_match_against = create_invoices(self.supplier, "inv", 1, 100) # So 120.00 is the due
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against, {"id": "matched_to"}, {"value": 120}) # Trying to match -130.00 when due is only -120.00
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
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )


class CreatePaymentNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):

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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


    # CORRECT USAGE
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
        headers = PurchaseHeader.objects.all().order_by("-pk")
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

    # CORRECT USAGE
    def test_negative_payment(self):
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
                "total": -120
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
            'PL'
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


    """

    Test matching for positive payments

    """

    # CORRECT USAGE
    def test_fully_matched_positive_payment(self):
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
        invoice_to_match = create_invoices(self.supplier, "inv", 1, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 120})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

        lines = PurchaseLine.objects.all()
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
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            1
        )

        header = payment

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


    # CORRECT USAGE
    def test_zero_value_match_positive_payment(self):
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
        invoice_to_match = create_invoices(self.supplier, "inv", 1, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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


        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = payment

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


    # INCORRECT USAGE
    def test_match_value_too_high(self):
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
        invoice_to_match = create_invoices(self.supplier, "inv", 1, 200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 120.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

    # INCORRECT USAGE
    def test_match_value_too_low(self):
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
        invoice_to_match = create_invoices(self.supplier, "inv", 1, -200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -0.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

    # CORRECT USAGE
    def test_match_ok_and_not_full_match(self):
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
        invoice_to_match = create_invoices(self.supplier, "inv", 1, 100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 60})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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

        header = payment

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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

    """
    Test matching for negative payments
    """

    # CORRECT USAGE
    def test_fully_matched_negative_payment_NEGATIVE(self):
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
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -120})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

        lines = PurchaseLine.objects.all()
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
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            1
        )

        header = payment

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


    # CORRECT USAGE
    def test_zero_value_match_negative_payment_NEGATIVE(self):
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
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

        lines = PurchaseLine.objects.all()
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
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = payment

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


    # INCORRECT USAGE
    def test_match_value_too_high_NEGATIVE(self):
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
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, -200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -120.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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


    # INCORRECT USAGE
    def test_match_value_too_low_NEGATIVE(self):
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
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, 200)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": 0.01})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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

    # CORRECT USAGE
    def test_match_ok_and_not_full_match_NEGATIVE(self):
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
                "total": -120
            }
        )
        invoice_to_match = create_invoices(self.supplier, "inv", 1, -100)[0]
        headers_as_dicts = [ to_dict(invoice_to_match) ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects([headers_to_match_against[0]], {"id": "matched_to"}, {"value": -60})

        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)

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
        tran = nom_trans[0]
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            tran.module,
            PL_MODULE
        )
        self.assertEqual(
            tran.header,
            payment.pk
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
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            payment.pk
        )
        tran = nom_trans[1]
        self.assertEqual(
            tran.line,
            2
        )
        self.assertEqual(
            tran.nominal,
            self.purchase_control
        )
        self.assertEqual(
            tran.value,
            -120
        )
        self.assertEqual(
            tran.ref,
            payment.ref
        )
        self.assertEqual(
            tran.period,
            PERIOD
        )     
        self.assertEqual(
            tran.date,
            payment.date
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
            1
        )

        header = payment

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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


"""
EDIT
"""

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
            '<select name="header-type" class="transaction-type-select" disabled required id="id_header-type">'
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

    # INCORRECT USAGE
    # Based on test_1
    # header is invalid but matching is ok
    def test_header_is_invalid_but_matching_is_ok(self):

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
                "supplier": 999999999,
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
        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            '<li>Select a valid choice. That choice is not one of the available choices.</li>',
            html=True
        )

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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -500.00</li>',
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
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1500.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -800.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2000.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -800.00</li>',
            html=True
        )

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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -900.00</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -1000.00</li>',
            html=True
        )


class EditPaymentNominalEntries(TestCase):

    @classmethod
    def setUpTestData(cls):

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

        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

        cls.url = reverse("purchases:create")


    # CORRECT USAGE
    # A non-zero payment is reduced
    def test_non_zero_payment(self):

        create_payment_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120,
                "due": 120,
                "paid": 0,
                "period": PERIOD
            },
            self.purchase_control,
            self.nominal
        )

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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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
            -100
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

    # CORRECT USAGE
    def test_non_zero_payment_is_changed_to_zero(self):

        create_payment_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120,
                "due": 120,
                "paid": 0,
                "period": PERIOD
            },
            self.purchase_control,
            self.nominal
        )

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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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

    # CORRECT USAGE
    def test_zero_payment_is_changed_to_non_zero(self):

        create_payment_with_nom_entries(
            {
                "cash_book": self.cash_book,
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 0,
                "due": 0,
                "paid": 0,
                "period": PERIOD
            },
            self.purchase_control,
            self.nominal
        )

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
            # 1 is the bank nominal
            # 1 is the control account
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
                "type": "pp",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 120
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)    
        self.assertEqual(response.status_code, 302)

        headers = PurchaseHeader.objects.all().order_by("pk")
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

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'PL'
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

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_1(self):

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Create a payment for 120.01
        # Create a refund for 120.00
        # Create a payment for -0.01

        # edit the first payment with a match value which isn't allowed because not enough outstanding
        # on the payment for -0.01

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
                "type": "pr",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
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

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            3
        )

    # INCORRECT USAGE
    def test_new_matched_value_is_ok_for_transaction_being_edited_but_not_for_matched_transaction_2(self):

        # Create an invoice for 120.01 through view first
        # Second create a credit note for 120.00
        # Third create an invoice for -0.01 and match the other two to it
        # Invalid edit follows

        # Create a payment for 120.01
        # Create a refund for 120.00
        # Create a payment for -0.01

        # edit the first payment with a match value which isn't allowed because not enough outstanding
        # on the payment for -0.01

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.01
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
                "type": "pr",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120.00
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
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
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
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

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pp",
                "cash_book": self.cash_book.pk,
                "supplier": self.supplier.pk,
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
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        matching_data["match-INITIAL_FORMS"] = 1
        data.update(matching_data)

        response = self.client.post(reverse("purchases:edit", kwargs={"pk": headers[0].pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            3
        )

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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -2400</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -100</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 2400</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 100</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and -120</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120</li>',
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
            '<li class="py-1">Please ensure the total of the transactions you are matching is between 0 and 120</li>',
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

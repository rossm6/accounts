from datetime import datetime, timedelta
from itertools import chain

from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from items.models import Item
from nominals.models import Nominal
from vat.models import Vat

from ..helpers import create_invoices, create_payments
from ..models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier
from ..views import create


"""

    Remember the transaction type is specified by a query paramter.  When creating the API -

    We could create methods:

        Purchase.create.payment() # which under the hood sets t='p' and POSTs to correct URI


    Need to test the sign for credit note and refund too

"""


HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
MATCHING_FORM_PREFIX = "match"


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
            type=type
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
            type=type
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

        cls.item = Item.objects.create(code="aa", description="aa-aa")
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

        cls.url = reverse("purchases:create_invoice")

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



    """
    In this section tests putting on a zero value transaction which can only be put on to match
    other transactions.

    First we test putting on a zero value invoice and then we test putting on a zero value payment.
    This way we hit both branches of the code.

    """


    def test_invoice_with_positive_input_is_saved_as_positive(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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


    def test_invoice_with_negative_input_is_saved_as_negative(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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
    # THIS IS A ZERO VALUE HEADER TRANSACTION
    # WHICH IS THE WAY TO MATCH OTHER TRANSACTIONS
    # E.G. AN INVOICE AND CREDIT NOTE ON THE SUPPLIER ACCOUNT NEED MATCHING
    def test_header_total_is_zero_with_no_lines_and_matching_transactions_equal_zero(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "i",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "i", 100)
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
            "type": "i",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "due_date": self.due_date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "i", 100)
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


    # INCORRECT USUAGE
    def test_header_total_is_zero_with_no_lines_with_no_matching_transactions(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "i",
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
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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


    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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

    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_zero_with_lines_and_with_matching_transactions_have_same_sign_as_new_header(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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

    # CORRECT USAGE
    # CHECK THE TOTAL OF THE LINES THEREFORE EQUALS THE TOTAL ENTERED
    def test_header_total_is_non_zero_and_with_lines_which_total_entered_total_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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
                "type": "i",
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
                "type": "i",
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

    def test_illegal_matching_situation_2(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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

    def test_illegal_matching_situation_3(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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

    def test_illegal_matching_situation_4(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "i",
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
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

        cls.url = reverse("purchases:create_payment")


    def test_payment_with_positive_input_is_saved_as_negative(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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

    def test_payment_with_negative_input_is_saved_as_positive(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
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
            "type": "p",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "p", 100)
        headers_to_match_against_orig = headers_to_match_against
        headers_as_dicts = [ to_dict(header) for header in headers_to_match_against ]
        headers_to_match_against = [ get_fields(header, ['type', 'ref', 'total', 'paid', 'due', 'id']) for header in headers_as_dicts ]
        matching_forms = []
        matching_forms += add_and_replace_objects(headers_to_match_against[:5], {"id": "matched_to"}, {"value": 100})
        matching_forms += add_and_replace_objects(headers_to_match_against[5:], {"id": "matched_to"}, {"value": -100})
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, matching_forms)
        data.update(matching_data)
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
            "type": "p",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        headers_to_match_against = create_cancelling_headers(10, self.supplier, "match", "p", 100)
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
        data.update(matching_data)
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

    # INCORRECT USUAGE
    def test_header_total_is_zero_and_with_no_matching_transactions(self):

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "p",
            "supplier": self.supplier.pk,
            "ref": self.ref,
            "date": self.date,
            "total": 0
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(MATCHING_FORM_PREFIX, [])
        data.update(matching_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(PurchaseHeader.objects.all()),
            0
        )
        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)

    # CORRECT USAGE -- BUT THIS MEANS THE TOTAL OF THE LINES IS USED FOR THE HEADER
    # SO THIS IS NOT A ZERO VALUE MATCHING TRANSACTION
    def test_header_total_is_non_zero_and_no_matching_transactions_selected(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 100
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
                "type": "p",
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
        data.update(matching_data)
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
                "type": "p",
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
        data.update(matching_data)
        # WE ARE CREATING A NEW INVOICE FOR 2400.00 and matching against -1000 worth of invoices (across 10 invoices)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        headers = PurchaseHeader.objects.all()
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
                "type": "p",
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
        data.update(matching_data)
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


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_non_zero_and_with_matching_transactions_have_same_sign_as_new_header(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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
        data.update(matching_data)
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
                "type": "p",
                "supplier": self.supplier.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -100
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
                "type": "p",
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
        data.update(matching_data)
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
                "type": "p",
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
        data.update(matching_data)
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
                "type": "p",
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
        data.update(matching_data)
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


    # INCORRECT - Cannot match header to matching transactions with same sign
    def test_header_total_is_non_zero_and_with_matching_transactions_have_same_sign_as_new_header_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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
        data.update(matching_data)
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
                "type": "p",
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
        data.update(matching_data)
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

    def test_illegal_matching_situation_2(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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
        data.update(matching_data)
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

    def test_illegal_matching_situation_3(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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
        data.update(matching_data)
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

    def test_illegal_matching_situation_4(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "p",
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
        data.update(matching_data)
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
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
from vat.models import Vat

from ..helpers import (create_credit_note_with_lines,
                       create_credit_note_with_nom_entries,
                       create_invoice_with_lines,
                       create_invoice_with_nom_entries, create_invoices,
                       create_lines, create_payment_with_nom_entries,
                       create_payments, create_refund_with_nom_entries)
from ..models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
PERIOD = '202007'  # the calendar month i made the change !
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


class GeneralTransactionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="dummy", password="dummy")
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
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(
            parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        cls.cash_book = CashBook.objects.create(
            name="Cash Book", nominal=cls.nominal)  # Bank Nominal
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("purchases:create")

    # CORRECT USAGE
    def test_approve_and_another_redirection(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
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
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "pi",
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

    # INCORRECT USAGE
    # Try and change the tran type from purchase brought forward refund
    # to purchase refund
    # Trans types should never be allowed because it would sometimes the
    # matching would never to be changed or deleted
    # In which case just void the transaction

    def test_type_cannot_be_changed(self):
        self.client.force_login(self.user)

        PurchaseHeader.objects.create(**{
            "cash_book": self.cash_book,
            "type": "pbr",
            "supplier": self.supplier,
            "ref": self.ref,
            "date": self.model_date,
            "due_date": self.model_due_date,
            "total": 120,
            "due": 120,
            "paid": 0,
            "goods": 0,
            "vat": 0,
            "period": self.period
        })

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.type,
            "pbr"
        )
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
                "cash_book": self.cash_book.pk,
                "type": "pr",
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
            header.type,
            "pbr"
        )
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

    # INCORRECT USAGE
    def test_voided_transactions_cannot_be_edited(self):
        self.client.force_login(self.user)

        PurchaseHeader.objects.create(**{
            "cash_book": self.cash_book,
            "type": "pbr",
            "supplier": self.supplier,
            "ref": self.ref,
            "date": self.model_date,
            "due_date": self.model_due_date,
            "total": 120,
            "due": 120,
            "paid": 0,
            "goods": 0,
            "vat": 0,
            "period": self.period,
            "status": "v"
        })

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.type,
            "pbr"
        )
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
        self.assertEqual(
            header.status,
            "v"
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "cash_book": self.cash_book.pk,
                "type": "pr",
                "supplier": self.supplier.pk,
				"period": self.period.pk,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "total": 100,
                "status": "c"
            }
        )
        data.update(header_data)
        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("purchases:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]

        headers = PurchaseHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertEqual(
            header.type,
            "pbr"
        )
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
        self.assertEqual(
            header.status,
            "v"
        )

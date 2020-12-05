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
from sales.helpers import (create_credit_note_with_lines,
                           create_credit_note_with_nom_entries,
                           create_invoice_with_lines,
                           create_invoice_with_nom_entries, create_invoices,
                           create_lines, create_receipt_with_nom_entries,
                           create_receipts, create_refund_with_nom_entries,
                           create_vat_transactions)
from sales.models import Customer, SaleHeader, SaleLine, SaleMatching
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
PERIOD = '202007'  # the calendar month i made the change !
SL_MODULE = "SL"
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


class VoidTransactionsTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.sale_control = Nominal.objects.create(
            parent=current_assets, name="Sales Ledger Control"
        )
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")
        # Cash book
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)


    # INCORRECT USAGE
    def test_voiding_an_invoice_already_voided(self):
        self.client.force_login(self.user)

        create_invoice_with_lines(
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
                "status": "v"
            },
            [
                {
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20
        )

        headers = SaleHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = SaleLine.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'v'
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
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )
    
        headers = SaleHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = SaleLine.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'v'
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
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_voiding_an_invoice_without_matching(self):
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
                "due": 2400
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

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        vat_transactions = VatTransaction.objects.all()
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
            headers[0].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

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
                self.sale_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
            )


        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'v'
        )


        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
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
                line.vat_transaction,
                None
            )

        matches = SaleMatching.objects.all()
        self.assertEqual(len(matches), 0)


    def test_voiding_an_invoice_with_matching_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)

        invoice = create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
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
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20,
            self.vat_nominal,
            self.sale_control
        )


        receipt =create_receipts(self.customer, "receipt", 1, self.period, 600)[0]
        match(invoice, [ (receipt, -600) ] )

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            2
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            600
        )
        self.assertEqual(
            headers[0].due,
            1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        receipt = headers[1]

        self.assertEqual(
            receipt.type,
            "sp"
        )
        self.assertEqual(
            receipt.total,
            -600
        )
        self.assertEqual(
            receipt.paid,
            -600
        )
        self.assertEqual(
            receipt.due,
            0
        )
        self.assertEqual(
            receipt.status,
            "c"
        )

        header = headers[0]

        matches = SaleMatching.objects.all()
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
            receipt
        )
        self.assertEqual(
            matches[0].value,
            -600
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

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
                self.sale_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
            )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
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
        self.assertEqual(
            headers[0].status,
            'v'
        )


        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        self.assertEqual(
            len(
                VatTransaction.objects.all()
            ),
            0
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
                line.vat_transaction,
                None
            )

        matches = SaleMatching.objects.all()
        self.assertEqual(len(matches), 0)

        # CHECK THE PAYMENT IS NOW CORRECT AFTER THE UNMATCHING

        receipt = headers[1]

        self.assertEqual(
            receipt.type,
            "sp"
        )
        self.assertEqual(
            receipt.total,
            -600
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -600
        )
        self.assertEqual(
            receipt.status,
            "c"
        )


    def test_voiding_an_invoice_with_matching_where_invoice_is_matched_to(self):
        self.client.force_login(self.user)

        invoice = create_invoice_with_nom_entries(
            {
                "type": "si",
                "customer": self.customer,
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
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20,
            self.vat_nominal,
            self.sale_control
        )


        receipt = create_receipts(self.customer, "receipt", 1, self.period, 600)[0]
        match(receipt, [ (invoice, 600) ] )

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        create_vat_transactions(headers[0], lines)

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            20
        )

        self.assertEqual(
            len(headers),
            2
        )
        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            600
        )
        self.assertEqual(
            headers[0].due,
            1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        receipt = headers[1]

        self.assertEqual(
            receipt.type,
            "sp"
        )
        self.assertEqual(
            receipt.total,
            -600
        )
        self.assertEqual(
            receipt.paid,
            -600
        )
        self.assertEqual(
            receipt.due,
            0
        )
        self.assertEqual(
            receipt.status,
            "c"
        )

        invoice = header = headers[0]

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            600
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

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
                self.sale_control
            )
            self.assertEqual(
                tran.field,
                "t"
            )
            self.assertEqual(
                lines[i].total_nominal_transaction,
                tran
            )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
        )

        invoice = header = headers[0]
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
            headers[0].status,
            'v'
        )


        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        self.assertEqual(
            len(
                VatTransaction.objects.all()
            ),
            0
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
                line.vat_transaction,
                None
            )

        matches = SaleMatching.objects.all()
        self.assertEqual(len(matches), 0)

        # CHECK THE PAYMENT IS NOW CORRECT AFTER THE UNMATCHING

        receipt = headers[1]

        self.assertEqual(
            receipt.type,
            "sp"
        )
        self.assertEqual(
            receipt.total,
            -600
        )
        self.assertEqual(
            receipt.paid,
            0
        )
        self.assertEqual(
            receipt.due,
            -600
        )
        self.assertEqual(
            receipt.status,
            "c"
        )

    # INCORRECT USAGE
    def test_brought_forward_invoice_already_voided(self):
        self.client.force_login(self.user)

        create_invoice_with_lines(
            {
                "type": "sbi",
                "customer": self.customer,
				"period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "total": 2400,
                "paid": 0,
                "due": 2400,
                "status": "v"
            },
            [
                {

                    'description': self.description,
                    'goods': 100,
                    'vat': 20
                }
            ] * 20,
        )

        headers = SaleHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = SaleLine.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'v'
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
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )

        headers = SaleHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = SaleLine.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'v'
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
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )


    # CORRECT USAGE
    def test_brought_forward_invoice_without_matching(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "sbi",
                "customer": self.customer,
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


        headers = SaleHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = SaleLine.objects.all()
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
        self.assertEqual(
            headers[0].status,
            'c'
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
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all().order_by("pk")
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
            headers[0].status,
            'v'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_brought_forward_invoice_with_matching_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "sbi",
                "customer": self.customer,
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

        invoice = header
        receipt = create_receipts(self.customer, "receipt", 1, self.period, 600)[0]
        match(invoice, [(receipt, -600)])

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            600
        )
        self.assertEqual(
            headers[0].due,
            1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        self.assertEqual(
            headers[1].total,
            -600
        )
        self.assertEqual(
            headers[1].paid,
            -600
        )
        self.assertEqual(
            headers[1].due,
            0
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        invoice = header = headers[0]
        receipt = headers[1]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
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
            receipt
        )
        self.assertEqual(
            matches[0].value,
            -600
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
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
            headers[0].status,
            'v'
        )

        self.assertEqual(
            headers[1].total,
            -600
        )
        self.assertEqual(
            headers[1].paid,
            0
        )
        self.assertEqual(
            headers[1].due,
            -600
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_brought_forward_invoice_with_matching_where_invoice_is_matched_to(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "sbi",
                "customer": self.customer,
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

        invoice = header
        receipt = create_receipts(self.customer, "receipt", 1, self.period, 600)[0]
        match(receipt, [(invoice, 600)])

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            2400
        )
        self.assertEqual(
            headers[0].paid,
            600
        )
        self.assertEqual(
            headers[0].due,
            1800
        )
        self.assertEqual(
            header.status,
            'c'
        )


        self.assertEqual(
            headers[1].total,
            -600
        )
        self.assertEqual(
            headers[1].paid,
            -600
        )
        self.assertEqual(
            headers[1].due,
            0
        )
        self.assertEqual(
            header.status,
            'c'
        )


        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        invoice = header = headers[0]
        receipt = headers[1]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            receipt
        )
        self.assertEqual(
            matches[0].matched_to,
            invoice
        )
        self.assertEqual(
            matches[0].value,
            600
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("sales:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("sales:transaction_enquiry")
        )
        headers = SaleHeader.objects.all().order_by("pk")
        self.assertEqual(
            len(headers),
            2
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
            headers[0].status,
            'v'
        )


        self.assertEqual(
            headers[1].total,
            -600
        )
        self.assertEqual(
            headers[1].paid,
            0
        )
        self.assertEqual(
            headers[1].due,
            -600
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )


        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]
        lines = SaleLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )
        lines = sort_multiple(lines, *[ (lambda l : l.pk, False) ])

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, None)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
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

        matches = SaleMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

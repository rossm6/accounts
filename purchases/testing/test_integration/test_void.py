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
                               create_payments, create_refund_with_nom_entries,
                               create_vat_transactions)
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


class VoidTransactionsTest(TestCase):

    @classmethod
    def setUpTestData(cls):
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
        # Cash book
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.nominal) # Bank Nominal
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.user = get_user_model().objects.create_superuser(username="dummy", password="dummy")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))
        # we will force login anyway so the user is just for this

    # INCORRECT USAGE
    def test_voiding_an_invoice_already_voided(self):
        self.client.force_login(self.user)

        create_invoice_with_lines(
            {
                "type": "pi",
                "supplier": self.supplier,
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

        headers = PurchaseHeader.objects.all()
        headers = sort_multiple(headers, *[ (lambda h : h.pk, False) ])

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0 # because it has already been voided
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
            self.assertEqual(
                line.vat_transaction,
                None
            )


        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        self.client.force_login(self.user)
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
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
            self.assertEqual(
                line.vat_transaction,
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
    def test_voiding_an_invoice_without_matching(self):
        self.client.force_login(self.user)

        create_invoice_with_nom_entries(
            {
                "type": "pi",
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
        data["void-id"] = header.pk
        self.client.force_login(self.user)
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
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

        lines = PurchaseLine.objects.all()
        self.assertEqual(
            len(lines),
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        nom_trans = sort_multiple(nom_trans, *[ (lambda n : n.pk, False) ])

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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


    def test_voiding_an_invoice_with_matching_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)

        invoice = create_invoice_with_nom_entries(
            {
                "type": "pi",
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
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20,
            self.vat_nominal,
            self.purchase_control
        )


        payment = create_payments(self.supplier, "payment", 1, self.period, 600)[0]
        match(invoice, [ (payment, -600) ] )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
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

        payment = headers[1]

        self.assertEqual(
            payment.type,
            "pp"
        )
        self.assertEqual(
            payment.total,
            -600
        )
        self.assertEqual(
            payment.paid,
            -600
        )
        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.status,
            "c"
        )

        header = headers[0]

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
            payment
        )
        self.assertEqual(
            matches[0].value,
            -600
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

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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


        lines = PurchaseLine.objects.all()
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


        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)

        # CHECK THE PAYMENT IS NOW CORRECT AFTER THE UNMATCHING

        payment = headers[1]

        self.assertEqual(
            payment.type,
            "pp"
        )
        self.assertEqual(
            payment.total,
            -600
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            -600
        )
        self.assertEqual(
            payment.status,
            "c"
        )



    def test_voiding_an_invoice_with_matching_where_invoice_is_matched_to(self):
        self.client.force_login(self.user)

        invoice = create_invoice_with_nom_entries(
            {
                "type": "pi",
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
                    'nominal': self.nominal,
                    'vat_code': self.vat_code,
                    'vat': 20
                }
            ] * 20,
            self.vat_nominal,
            self.purchase_control
        )


        payment = create_payments(self.supplier, "payment", 1, self.period, 600)[0]
        match(payment, [ (invoice, 600) ] )

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
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

        payment = headers[1]

        self.assertEqual(
            payment.type,
            "pp"
        )
        self.assertEqual(
            payment.total,
            -600
        )
        self.assertEqual(
            payment.paid,
            -600
        )
        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.status,
            "c"
        )

        invoice = header = headers[0]

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
            600
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

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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


        lines = PurchaseLine.objects.all()
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)

        # CHECK THE PAYMENT IS NOW CORRECT AFTER THE UNMATCHING

        payment = headers[1]

        self.assertEqual(
            payment.type,
            "pp"
        )
        self.assertEqual(
            payment.total,
            -600
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.due,
            -600
        )
        self.assertEqual(
            payment.status,
            "c"
        )

    # INCORRECT USAGE
    def test_brought_forward_invoice_already_voided(self):
        self.client.force_login(self.user)

        create_invoice_with_lines(
            {
                "type": "pbi",
                "supplier": self.supplier,
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
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
        self.assertEqual(
            headers[0].status,
            'v'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
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
            self.assertEqual(
                line.vat_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )


    # CORRECT USAGE
    def test_brought_forward_invoice_without_matching(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "pbi",
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

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
            self.assertEqual(
                line.vat_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_brought_forward_invoice_with_matching_where_invoice_is_matched_by(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "pbi",
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

        invoice = header
        payment = create_payments(self.supplier, "payment", 1, self.period, 600)[0]
        match(invoice, [(payment, -600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
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
        payment = headers[1]

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
            payment
        )
        self.assertEqual(
            matches[0].value,
            -600
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all()
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
            self.assertEqual(
                line.vat_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_brought_forward_invoice_with_matching_where_invoice_is_matched_to(self):
        self.client.force_login(self.user)

        header, lines = create_invoice_with_lines(
            {
                "type": "pbi",
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

        invoice = header
        payment = create_payments(self.supplier, "payment", 1, self.period, 600)[0]
        match(payment, [(invoice, 600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
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
        payment = headers[1]

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
            600
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all().order_by("pk")
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

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
        )

        header = headers[0]
        lines = PurchaseLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            20
        )

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
            self.assertEqual(
                line.vat_transaction,
                None
            )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )


    # INCORRECT USAGE
    def test_voiding_a_payment_already_voided(self):
        self.client.force_login(self.user)

        PurchaseHeader.objects.create(
            **
            {
                "type": "pp",
                "cash_book": self.cash_book,
                "supplier": self.supplier,
				"period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "total": -2400,
                "paid": 0,
                "due": -2400,
                "status": "v"
            }
        )

        headers = PurchaseHeader.objects.all()

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
        self.assertEqual(
            headers[0].status,
            'v'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )

        cash_book_trans = CashBookTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(cash_book_trans),
            0
        )

        header = headers[0]

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )
        
        headers = PurchaseHeader.objects.all()

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
        self.assertEqual(
            headers[0].status,
            'v'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )

        cash_book_trans = CashBookTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(cash_book_trans),
            0
        )

        header = headers[0]

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

    # CORRECT USAGE
    def test_voiding_a_payment_without_matching(self):
        self.client.force_login(self.user)

        create_payment_with_nom_entries(
            {
                "type": "pp",
                "cash_book": self.cash_book,
                "supplier": self.supplier,
				"period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            self.purchase_control,
            self.nominal
        )

        headers = PurchaseHeader.objects.all()

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
        self.assertEqual(
            headers[0].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            2
        )

        cash_book_trans = CashBookTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = headers[0]

        self.assertEqual(
            nom_trans[0].value,
            -2400
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.nominal
        )
        self.assertEqual(
            nom_trans[0].field,
            "t"
        )

        self.assertEqual(
            nom_trans[1].value,
            2400
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.purchase_control
        )
        self.assertEqual(
            nom_trans[1].field,
            "t"
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
            cash_book_trans[0].value,
            -2400
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
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
            headers[0].status,
            'v'
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # CORRECT USAGE
    def test_voiding_a_payment_with_matching_where_payment_is_matched_by(self):
        self.client.force_login(self.user)

        payment = create_payment_with_nom_entries(
            {
                "type": "pp",
                "cash_book": self.cash_book,
                "supplier": self.supplier,
				"period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            self.purchase_control,
            self.nominal
        )

        invoice = create_invoices(self.supplier, "inv", 1, self.period, 600)[0]

        match(payment, [(invoice, 600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        payment = headers[0]
        invoice = headers[1]

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            -600
        )
        self.assertEqual(
            headers[0].due,
            -1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        self.assertEqual(
            headers[1].total,
            720
        )
        self.assertEqual(
            headers[1].paid,
            600
        )
        self.assertEqual(
            headers[1].due,
            120
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            2
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = headers[0]

        self.assertEqual(
            nom_trans[0].value,
            -2400
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.nominal
        )
        self.assertEqual(
            nom_trans[0].field,
            "t"
        )

        self.assertEqual(
            nom_trans[1].value,
            2400
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.purchase_control
        )
        self.assertEqual(
            nom_trans[1].field,
            "t"
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
            cash_book_trans[0].value,
            -2400
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
            600
        )

        data = {}
        data["void-id"] = payment.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            2
        )
        payment = header = headers[0]
        invoice = headers[1]
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
            headers[0].status,
            'v'
        )

        self.assertEqual(
            invoice.total,
            720
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            720
        )
        self.assertEqual(
            invoice.status,
            'c'
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # CORRECT USAGE
    def test_voiding_a_payment_with_matching_where_payment_is_matched_to(self):
        self.client.force_login(self.user)

        payment = create_payment_with_nom_entries(
            {
                "type": "pp",
                "cash_book": self.cash_book,
                "supplier": self.supplier,
				"period": self.period,
                "ref": self.ref,
                "date": self.model_date,
                "total": 2400,
                "paid": 0,
                "due": 2400
            },
            self.purchase_control,
            self.nominal
        )

        invoice = create_invoices(self.supplier, "inv", 1, self.period, 600)[0]

        match(invoice, [(payment, -600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        payment = headers[0]
        invoice = headers[1]

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            -600
        )
        self.assertEqual(
            headers[0].due,
            -1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        self.assertEqual(
            headers[1].total,
            720
        )
        self.assertEqual(
            headers[1].paid,
            600
        )
        self.assertEqual(
            headers[1].due,
            120
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            2
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        header = headers[0]

        self.assertEqual(
            nom_trans[0].value,
            -2400
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.nominal
        )
        self.assertEqual(
            nom_trans[0].field,
            "t"
        )

        self.assertEqual(
            nom_trans[1].value,
            2400
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.purchase_control
        )
        self.assertEqual(
            nom_trans[1].field,
            "t"
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
            cash_book_trans[0].value,
            -2400
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            1
        )

        self.assertEqual(
            matches[0].matched_by,
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            payment
        )
        self.assertEqual(
            matches[0].value,
            -600
        )

        data = {}
        data["void-id"] = payment.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            2
        )
        payment = header = headers[0]
        invoice = headers[1]
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
            headers[0].status,
            'v'
        )

        self.assertEqual(
            invoice.total,
            720
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            720
        )
        self.assertEqual(
            invoice.status,
            'c'
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

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # CORRECT USAGE
    def test_voiding_a_brought_forward_payment_without_matching(self):
        self.client.force_login(self.user)

        payment = create_payments(self.supplier, "payment", 1, self.period, 2400)[0]

        headers = PurchaseHeader.objects.all()

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
        self.assertEqual(
            headers[0].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )

        header = headers[0]

        matches = PurchaseMatching.objects.all()
        self.assertEqual(
            len(matches),
            0
        )

        data = {}
        data["void-id"] = header.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": header.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
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
            headers[0].status,
            'v'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # CORRECT USAGE
    def test_voiding_a_brought_forward_payment_with_matching_where_payment_is_matched_by(self):
        self.client.force_login(self.user)

        payment = create_payments(self.supplier, "payment", 1, self.period, 2400)[0]

        invoice = create_invoices(self.supplier, "inv", 1, self.period, 600)[0]

        match(payment, [(invoice, 600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        payment = headers[0]
        invoice = headers[1]

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            -600
        )
        self.assertEqual(
            headers[0].due,
            -1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        self.assertEqual(
            headers[1].total,
            720
        )
        self.assertEqual(
            headers[1].paid,
            600
        )
        self.assertEqual(
            headers[1].due,
            120
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
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
            600
        )

        data = {}
        data["void-id"] = payment.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": payment.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            2
        )
        payment = header = headers[0]
        invoice = headers[1]
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
            headers[0].status,
            'v'
        )

        self.assertEqual(
            invoice.total,
            720
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            720
        )
        self.assertEqual(
            invoice.status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # CORRECT USAGE
    def test_voiding_a_brought_forward_payment_with_matching_where_payment_is_matched_to(self):
        self.client.force_login(self.user)

        payment = create_payments(self.supplier, "payment", 1, self.period, 2400)[0]

        invoice = create_invoices(self.supplier, "inv", 1, self.period, 600)[0]

        match(invoice, [(payment, -600)])

        headers = PurchaseHeader.objects.all().order_by("pk")

        payment = headers[0]
        invoice = headers[1]

        self.assertEqual(
            len(headers),
            2
        )

        self.assertEqual(
            headers[0].total,
            -2400
        )
        self.assertEqual(
            headers[0].paid,
            -600
        )
        self.assertEqual(
            headers[0].due,
            -1800
        )
        self.assertEqual(
            headers[0].status,
            'c'
        )

        self.assertEqual(
            headers[1].total,
            720
        )
        self.assertEqual(
            headers[1].paid,
            600
        )
        self.assertEqual(
            headers[1].due,
            120
        )
        self.assertEqual(
            headers[1].status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all().order_by("pk")
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
            invoice
        )
        self.assertEqual(
            matches[0].matched_to,
            payment
        )
        self.assertEqual(
            matches[0].value,
            -600
        )

        data = {}
        data["void-id"] = payment.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": payment.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("purchases:transaction_enquiry")
        )
        headers = PurchaseHeader.objects.all()
        self.assertEqual(
            len(headers),
            2
        )
        payment = header = headers[0]
        invoice = headers[1]
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
            headers[0].status,
            'v'
        )

        self.assertEqual(
            invoice.total,
            720
        )
        self.assertEqual(
            invoice.paid,
            0
        )
        self.assertEqual(
            invoice.due,
            720
        )
        self.assertEqual(
            invoice.status,
            'c'
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        matches = PurchaseMatching.objects.all()
        self.assertEqual(len(matches), 0)


    # INVALID
    def test_voiding_a_positive_payment_so_outstanding_would_be_invalid(self):
        self.client.force_login(self.user)
        payment = create_payments(self.supplier, "payment", 1, self.period, -1.00)[0]
        payment1 = create_payments(self.supplier, "payment", 1, self.period, 1201)[0]
        payment2 = create_payments(self.supplier, "payment", 1, self.period, -1200)[0]
        match(payment, [(payment1, -1201), (payment2, 1200)])

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            1.00
        )
        self.assertEqual(
            payment.total,
            1.00
        )

        self.assertEqual(
            payment1.due,
            0
        )
        self.assertEqual(
            payment1.paid,
            -1201
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1201
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        data = {}
        data["void-id"] = payment1.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": payment1.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            1.00
        )
        self.assertEqual(
            payment.total,
            1.00
        )

        self.assertEqual(
            payment1.due,
            0
        )
        self.assertEqual(
            payment1.paid,
            -1201
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1201
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    def test_voiding_a_negative_payment_so_outstanding_would_be_invalid(self):
        self.client.force_login(self.user)
        payment = create_payments(self.supplier, "payment", 1, self.period, -1.00)[0]
        payment1 = create_payments(self.supplier, "payment", 1, self.period, 1201)[0]
        payment2 = create_payments(self.supplier, "payment", 1, self.period, -1200)[0]
        match(payment, [(payment1, -1201), (payment2, 1200)])

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            1.00
        )
        self.assertEqual(
            payment.total,
            1.00
        )

        self.assertEqual(
            payment1.due,
            0
        )
        self.assertEqual(
            payment1.paid,
            -1201
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1201
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        data = {}
        data["void-id"] = payment2.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": payment2.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            1.00
        )
        self.assertEqual(
            payment.total,
            1.00
        )

        self.assertEqual(
            payment1.due,
            0
        )
        self.assertEqual(
            payment1.paid,
            -1201
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1201
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

    # INVALID
    def test_voiding_a_zero_payment_INVALID(self):
        self.client.force_login(self.user)
        payment = create_payments(self.supplier, "payment", 1, self.period, 0)[0]
        payment1 = create_payments(self.supplier, "payment", 1, self.period, 1201)[0]
        payment2 = create_payments(self.supplier, "payment", 1, self.period, -1200)[0]
        match(payment, [(payment1, -1200), (payment2, 1200)])

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.total,
            0
        )

        self.assertEqual(
            payment1.due,
            -1
        )
        self.assertEqual(
            payment1.paid,
            -1200
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )

        data = {}
        data["void-id"] = payment1.pk
        response = self.client.post(reverse("purchases:void", kwargs={"pk": payment1.pk}), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )

        payment.refresh_from_db()
        payment1.refresh_from_db()
        payment2.refresh_from_db()

        self.assertEqual(
            payment.due,
            0
        )
        self.assertEqual(
            payment.paid,
            0
        )
        self.assertEqual(
            payment.total,
            0
        )

        self.assertEqual(
            payment1.due,
            -1
        )
        self.assertEqual(
            payment1.paid,
            -1200
        )
        self.assertEqual(
            payment1.total,
            -1201
        )

        self.assertEqual(
            payment2.due,
            0
        )
        self.assertEqual(
            payment2.paid,
            1200
        )
        self.assertEqual(
            payment2.total,
            1200
        )

        matches = PurchaseMatching.objects.all().order_by("pk")
        self.assertEqual(
            len(matches),
            2
        )

        self.assertEqual(
            matches[0].matched_by,
            payment
        )
        self.assertEqual(
            matches[0].matched_to,
            payment1
        )
        self.assertEqual(
            matches[0].value,
            -1200
        )
        self.assertEqual(
            matches[0].period,
            self.period
        )
        self.assertEqual(
            matches[1].matched_by,
            payment
        )
        self.assertEqual(
            matches[1].matched_to,
            payment2
        )
        self.assertEqual(
            matches[1].value,
            1200
        )
        self.assertEqual(
            matches[1].period,
            self.period
        )
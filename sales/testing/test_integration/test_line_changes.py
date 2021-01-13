"""
Tests for editing an aspect of a line and checking the right things happen
"""

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
SL_MODULE = "SL"
DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'


class LineChanges(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.customer = Customer.objects.create(name="test_customer")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (
            datetime.now() + timedelta(days=31)).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.sale_control = Nominal.objects.create(
            parent=current_assets, name="Sales Ledger Control"
        )
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    # CORRECT USAGE
    def test_change_vat_code_to_no_vat_code(self):
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
            self.sale_control
        )

        headers = SaleHeader.objects.all().order_by("pk")

        lines = SaleLine.objects.all().order_by("pk")
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

        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])

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
                nom_trans[3 * i]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[(3 * i) + 1]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[(3 * i) + 2]
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
                "SL"
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
                "o"
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
            sum(vat_tran.goods for vat_tran in vat_transactions)
        )

        self.assertEqual(
            header.vat,
            sum(vat_tran.vat for vat_tran in vat_transactions)
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
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "customer": header.customer.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                "total": header.total
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        for form in line_forms:
            form["vat_code"] = ""
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = SaleHeader.objects.all()
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
        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = (
            SaleLine.objects
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
            0
        )
        lines = list(lines)
        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[3 * i]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[(3 * i) + 1]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[(3 * i) + 2]
            )
            self.assertEqual(
                line.vat_transaction,
                None
            )

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for tran in goods_nom_trans:
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

        for tran in vat_nom_trans:
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

        for tran in total_nom_trans:
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

        matches = SaleMatching.objects.all()
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


    # CORRECT USAGE
    def test_no_vat_code_changed_to_vat_code(self):
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
                "due": 2400,
                "goods": 2000,
                "vat": 400
            },
            [
                {
                    'description': self.description,
                    'goods': 100,
                    'nominal': self.nominal,
                    'vat_code': None,
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

        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
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

        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])

        header = headers[0]

        for i, line in enumerate(lines):
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, None)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[3 * i]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[(3 * i) + 1]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[(3 * i) + 2]
            )
            self.assertEqual(
                line.vat_transaction,
                None
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
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "customer": header.customer.pk,
                "period": header.period.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "due_date": header.due_date.strftime(DATE_INPUT_FORMAT),
                "total": header.total
            }
        )
        data.update(header_data)

        lines_as_dicts = [to_dict(line) for line in lines]
        line_trans = [get_fields(line, ['id',  'description', 'goods',
                                        'nominal', 'vat_code', 'vat']) for line in lines_as_dicts]
        line_forms = line_trans
        for form in line_forms:
            form["vat_code"] = self.vat_code.pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 20
        data.update(line_data)

        matching_data = create_formset_data(match_form_prefix, [])
        data.update(matching_data)

        url = reverse("sales:edit", kwargs={"pk": headers[0].pk})

        response = self.client.post(url, data)

        headers = SaleHeader.objects.all()
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
        nom_trans = sort_multiple(nom_trans, *[(lambda n: n.pk, False)])
        self.assertEqual(
            len(nom_trans),
            20 + 20 + 20
        )

        header = headers[0]
        lines = (
            SaleLine.objects
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
            self.assertEqual(line.line_no, i + 1)
            self.assertEqual(line.header, header)
            self.assertEqual(line.description, self.description)
            self.assertEqual(line.goods, 100)
            self.assertEqual(line.nominal, self.nominal)
            self.assertEqual(line.vat_code, self.vat_code)
            self.assertEqual(line.vat, 20)
            self.assertEqual(
                line.goods_nominal_transaction,
                nom_trans[3 * i]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                nom_trans[(3 * i) + 1]
            )
            self.assertEqual(
                line.total_nominal_transaction,
                nom_trans[(3 * i) + 2]
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
                "SL"
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
                "o"
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

        goods_nom_trans = nom_trans[::3]
        vat_nom_trans = nom_trans[1::3]
        total_nom_trans = nom_trans[2::3]

        for tran in goods_nom_trans:
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

        for tran in vat_nom_trans:
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

        for tran in total_nom_trans:
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

        matches = SaleMatching.objects.all()
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
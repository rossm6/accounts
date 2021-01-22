from datetime import date, datetime
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.helpers import *
from cashbook.models import (CashBook, CashBookHeader, CashBookLine,
                             CashBookTransaction)
from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = 'header'
LINE_FORM_PREFIX = 'line'
DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

class CreateBroughtForwardPayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.not_bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Not Bank Nominal")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(
            parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        # Cash book
        cls.cash_book = CashBook.objects.create(
            name="Cash Book", nominal=cls.bank_nominal)  # Bank Nominal
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("cashbook:create") + "?t=cp"
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    def test_get_request_with_query_param(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("cashbook:create") + "?t=cbp")
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp" selected>Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp">Payment</option>'
            '<option value="cr">Receipt</option>'
            '</select>',
            html=True
        )

    def test_create_single_line_POSITIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cbp",
				"period": self.period.pk,
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 120
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": 100,
                "vat": 20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            -20
        )
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.vat_type,
            None
        )

        lines = CashBookLine.objects.all()
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )

        self.assertEqual(
            len(lines),
            1
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
    def test_create_zero_payment_with_no_lines(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cbp",
				"period": self.period.pk,
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 0,
            }
        )
        data.update(header_data)
        line_data = create_formset_data(LINE_FORM_PREFIX, [])
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<li class="py-1">Cash book transactions cannot be for a zero value.</li>',
            html=True
        )

    def test_create_with_two_lines_POSITIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cbp",
				"period": self.period.pk,
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 240,
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": 100,
                "vat": 20
            }
        ] * 2
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -200
        )
        self.assertEqual(
            header.vat,
            -40
        )
        self.assertEqual(
            header.total,
            -240
        )
        self.assertEqual(
            header.vat_type,
            None
        )

        lines = CashBookLine.objects.all()
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

        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        self.assertEqual(
            lines[1].description,
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            None
        )
        self.assertEqual(
            lines[1].vat_code,
            None
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            -240
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

    def test_create_single_line_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cbp",
				"period": self.period.pk,
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120,
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            100
        )
        self.assertEqual(
            header.vat,
            20
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            None
        )

        lines = CashBookLine.objects.all()
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

        self.assertEqual(
            len(lines),
            1
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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


    def test_create_with_two_lines_NEGATIVE(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cbp",
				"period": self.period.pk,
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -240,
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ] * 2
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            200
        )
        self.assertEqual(
            header.vat,
            40
        )
        self.assertEqual(
            header.total,
            240
        )
        self.assertEqual(
            header.vat_type,
            None
        )

        lines = CashBookLine.objects.all()
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        self.assertEqual(
            len(lines),
            2
        )
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
        )

        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        self.assertEqual(
            lines[1].description,
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            100
        )
        self.assertEqual(
            lines[1].nominal,
            None
        )
        self.assertEqual(
            lines[1].vat_code,
            None
        )
        self.assertEqual(
            lines[1].vat,
            20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            240
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

class EditBroughtForwardPayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        cls.user = get_user_model().objects.create_superuser(username="dummy", password="dummy")
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.not_bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Not Bank Nominal")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(
            parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_liabilities, name="Vat")
        # Cash book
        cls.cash_book = CashBook.objects.create(
            name="Cash Book", nominal=cls.bank_nominal)  # Bank Nominal
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        cls.url = reverse("cashbook:create") + "?=cp"
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    def test_get_request(self):
        self.client.force_login(self.user)

        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": -120,
            "goods": -100,
            "vat": -20,
        })
        lines = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            -20
        )
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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

        response = self.client.get(
            reverse("cashbook:edit", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertContains(
            response,
            '<select name="header-type" class="form-control form-control-sm transaction-type-select" required disabled id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp" selected>Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp">Payment</option>'
            '<option value="cr">Receipt</option>'
            '</select>',
            html=True
        )

    def test_edit_single_line_POSITIVE(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": -120,
            "goods": -100,
            "vat": -20,
        })
        lines = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            -20
        )
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
                "type": header.type,
				"period": header.period.pk,
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 240,
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 200,
                "vat": 40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(
            reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -200
        )
        self.assertEqual(
            header.vat,
            -40
        )
        self.assertEqual(
            header.total,
            -240
        )
        self.assertEqual(
            header.vat_type,
            None
        )

        lines = CashBookLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -200
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            -240
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )


    def test_create_new_line(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": -120,
            "goods": -100,
            "vat": -20,
        })
        lines = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            -20
        )
        self.assertEqual(
            header.total,
            -120
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
                "type": header.type,
				"period": header.period.pk,
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 360,
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 100,
                "vat": 20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": 200,
                "vat": 40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(
            reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )

        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -300
        )
        self.assertEqual(
            header.vat,
            -60
        )
        self.assertEqual(
            header.total,
            -360
        )

        lines = CashBookLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )
        vat_transactions = VatTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(vat_transactions),
            0
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        self.assertEqual(
            lines[1].description,
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            -200
        )
        self.assertEqual(
            lines[1].nominal,
            None
        )
        self.assertEqual(
            lines[1].vat_code,
            None
        )
        self.assertEqual(
            lines[1].vat,
            -40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            -360
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

    def test_edit_single_line_NEGATIVE(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": 120,
            "goods": 100,
            "vat": 20,
        })
        lines = [
            {
                "description": self.description,
                "goods": 100,
                "vat": 20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            100
        )
        self.assertEqual(
            header.vat,
            20
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
				"period": header.period.pk,
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": -240,
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -200,
                "vat": -40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(
            reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            200
        )
        self.assertEqual(
            header.vat,
            40
        )
        self.assertEqual(
            header.total,
            240
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            200
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )

        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )

        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            240
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

    def test_create_new_line_NEGATIVE(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": 120,
            "goods": 100,
            "vat": 20,
        })
        lines = [
            {
                "description": self.description,
                "goods": 100,
                "vat": 20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            100
        )
        self.assertEqual(
            header.vat,
            20
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
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
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
				"period": header.period.pk,
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": -360,
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -100,
                "vat": -20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": -200,
                "vat": -40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(
            reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            302
        )
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            300
        )
        self.assertEqual(
            header.vat,
            60
        )
        self.assertEqual(
            header.total,
            360
        )
        self.assertEqual(
            header.vat_type,
            None
        )
        lines = CashBookLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            0
        )
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            0
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_transaction,
            None
        )
        self.assertEqual(
            lines[1].description,
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            200
        )
        self.assertEqual(
            lines[1].nominal,
            None
        )
        self.assertEqual(
            lines[1].vat_code,
            None
        )
        self.assertEqual(
            lines[1].vat,
            40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[1].vat_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
            360
        )
        self.assertEqual(
            cash_book_trans[0].field,
            't'
        )
        self.assertEqual(
            cash_book_trans[0].type,
            header.type
        )

    def test_cannot_edit_to_zero(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": -120,
            "goods": -100,
            "vat": -20
        })
        lines = [
            {
                "description": self.description,
                "goods": -100,
                "vat": -20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            header.cash_book,
            self.cash_book
        )
        self.assertEqual(
            header.goods,
            -100
        )
        self.assertEqual(
            header.vat,
            -20
        )
        self.assertEqual(
            header.total,
            -120
        )
        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            0
        )
        self.assertEqual(
            lines[0].description,
            self.description
        )
        self.assertEqual(
            lines[0].goods,
            -100
        )
        self.assertEqual(
            lines[0].nominal,
            None
        )
        self.assertEqual(
            lines[0].vat_code,
            None
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            None
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            None
        )
        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )
        self.assertEqual(
            cash_book_trans[0].module,
            'CB'
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
                "type": header.type,
				"period": header.period.pk,
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 0
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -100,
                "vat": -20,
                "DELETE": "yes"
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": -200,
                "vat": -40,
                "DELETE": "yes"
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(
            reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<li class="py-1">Cash book transactions cannot be for a zero value.</li>',
            html=True
        )
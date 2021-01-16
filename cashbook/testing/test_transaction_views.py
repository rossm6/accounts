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

class ViewPayment(TestCase):

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

    def test(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cp",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": -120,
            "goods": -100,
            "vat": -20,
            "vat_type": "o"
        })
        lines = [
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.not_bank_nominal,
                "vat_code": self.vat_code,
                "vat": -20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        nom_trans = create_nom_trans(
            NominalTransaction, CashBookLine, header, lines, self.bank_nominal, self.vat_nominal)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        create_vat_transactions(header, lines)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        response = self.client.get(
            reverse("cashbook:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            response.context["header"],
            header
        )


class ViewBroughtForwardPayment(TestCase):

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

    def test(self):
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
        response = self.client.get(
            reverse("cashbook:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            response.context["header"],
            header
        )

class ViewReceipt(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, 
            period="01", 
            fy_and_period="202001", 
            month_start=date(2020,1,31)
        )
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
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )


    def test_get_request(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cr",
			"period": self.period,
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.model_date,
            "total": 120,
            "goods": 100,
            "vat": 20,
            "vat_type": "o"
        })
        lines = [
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.not_bank_nominal,
                "vat_code": self.vat_code,
                "vat": 20
            }
        ]
        lines = create_lines(CashBookLine, header, lines)
        nom_trans = create_nom_trans(
            NominalTransaction, CashBookLine, header, lines, self.bank_nominal, self.vat_nominal)
        cash_book_trans = create_cash_book_trans(CashBookTransaction, header)
        create_vat_transactions(header, lines)
        headers = CashBookHeader.objects.all()
        header = headers[0]
        self.assertEqual(
            len(headers),
            1
        )
        response = self.client.get(
            reverse("cashbook:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            response.context["header"],
            header
        )


class ViewBroughtForwardReceipt(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy,
            period="01",
            fy_and_period="202001",
            month_start=date(2020, 1, 31)
        )
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
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
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    def test_get_request(self):
        self.client.force_login(self.user)
        header = CashBookHeader.objects.create(**{
            "type": "cbr",
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
        response = self.client.get(
            reverse("cashbook:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            response.context["header"],
            header
        )
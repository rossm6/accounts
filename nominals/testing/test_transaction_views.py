from datetime import date, datetime, timedelta
from itertools import chain
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import create_formset_data, create_header
from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone
from nominals.helpers import (create_nominal_journal,
                              create_nominal_journal_without_nom_trans,
                              create_vat_transactions)
from nominals.models import (Nominal, NominalHeader, NominalLine,
                             NominalTransaction)
from vat.models import Vat, VatTransaction

"""
These tests just check that the nominal module uses the accountancy general classes correctly.
The testing of these general classes is done in the purchase ledger.
"""

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'


class ViewJournal(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.ref = "test journal"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.debtors_nominal = Nominal.objects.create(
            parent=current_assets, name="Trade Debtors")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_assets, name="Vat")
        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)
        ModuleSettings.objects.create(
            cash_book_period=cls.period,
            nominals_period=cls.period,
            purchases_period=cls.period,
            sales_period=cls.period
        )

    def test(self):
        self.client.force_login(self.user)
        header, lines, nominal_transactions = create_nominal_journal({
            "header": {
                "type": "nj",
                "ref": "test journal",
                "period": self.period,
                "date": self.model_date,
                "total": 120,
                "vat_type": "o"
            },
            "lines": [
                {
                    "line_no": 1,
                    "description": "line 1",
                    "goods": 100,
                    "nominal": self.bank_nominal,
                    "vat_code": self.vat_code,
                    "vat": 20
                },
                {
                    "line_no": 2,
                    "description": "line 2",
                    "goods": -100,
                    "nominal": self.debtors_nominal,
                    "vat_code": self.vat_code,
                    "vat": -20
                }
            ],
        },
            self.vat_nominal
        )
        headers = NominalHeader.objects.all()
        self.assertEqual(len(headers), 1)
        header = headers[0]
        response = self.client.get(
            reverse("nominals:view", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertEqual(
            response.context["header"],
            header
        )
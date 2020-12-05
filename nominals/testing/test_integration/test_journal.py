from datetime import date, datetime, timedelta
from itertools import chain
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import create_formset_data, create_header
from controls.models import FinancialYear, Period
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

class CreateJournal(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.factory = RequestFactory()
        cls.ref = "test journal"
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
        cls.url = reverse("nominals:create")

    # CORRECT USAGE
    # Can request create journal view t=nj GET parameter

    def test_get_request_with_query_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url + "?t=nj")
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="nj" selected="selected">Journal</option>'
            '</select>',
            html=True
        )

    # CORRECT USAGE
    # Can request create journal view without GET parameter
    def test_get_request_with_query_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="nj" selected="selected">Journal</option>'
            '</select>',
            html=True
        )

    # CORRECT USAGE
    # Each line contains non-zero goods and vat
    def test_create_journal(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": 120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 20
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -20
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            'nj',
        )
        self.assertEqual(
            header.ref,
            self.ref,
        )
        self.assertEqual(
            header.period,
            self.period
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
            "o"
        )
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            len(vat_transactions),
            2
        )
        debit = lines[0]
        credit = lines[1]
        # DEBIT
        self.assertEqual(
            debit.description,
            self.description
        )
        self.assertEqual(
            debit.goods,
            100
        )
        self.assertEqual(
            debit.nominal,
            self.bank_nominal
        )
        self.assertEqual(
            debit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            debit.vat,
            20
        )
        self.assertEqual(
            debit.goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            debit.vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            debit.vat_transaction,
            vat_transactions[0]
        )
        # CREDIT
        self.assertEqual(
            credit.description,
            self.description
        )
        self.assertEqual(
            credit.goods,
            -100
        )
        self.assertEqual(
            credit.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            credit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            credit.vat,
            -20
        )
        self.assertEqual(
            credit.goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            credit.vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            credit.vat_transaction,
            vat_transactions[1]
        )
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        # debit goods
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            debit.pk
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            100
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[0].field,
            "g"
        )
        # debit vat
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            debit.pk
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            20
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[1].field,
            "v"
        )
        # credit goods
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            credit.pk
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            -100
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[2].field,
            "g"
        )
        # credit vat
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            credit.pk
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            -20
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[3].field,
            "v"
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
                "NL"
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

    # CORRECT USAGE
    # Each line contains goods only

    def test_create_journal_with_goods_only_and_not_vat(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": 120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 120,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 0
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": -120,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -0
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            'nj',
        )
        self.assertEqual(
            header.ref,
            self.ref,
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.goods,
            120
        )
        self.assertEqual(
            header.vat,
            0
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(lines),
            2
        )
        debit = lines[0]
        credit = lines[1]
        # DEBIT
        self.assertEqual(
            debit.description,
            self.description
        )
        self.assertEqual(
            debit.goods,
            120
        )
        self.assertEqual(
            debit.nominal,
            self.bank_nominal
        )
        self.assertEqual(
            debit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            debit.vat,
            0
        )
        self.assertEqual(
            debit.goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            debit.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            debit.vat_transaction,
            vat_transactions[0]
        )
        # CREDIT
        self.assertEqual(
            credit.description,
            self.description
        )
        self.assertEqual(
            credit.goods,
            -120
        )
        self.assertEqual(
            credit.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            credit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            credit.vat,
            0
        )
        self.assertEqual(
            credit.goods_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            credit.vat_nominal_transaction,
            None
        )
        self.assertEqual(
            credit.vat_transaction,
            vat_transactions[1]
        )
        self.assertEqual(
            len(nominal_transactions),
            2
        )
        # debit goods
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            debit.pk
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            120
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[0].field,
            "g"
        )
        # credit goods
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            credit.pk
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            -120
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[1].field,
            "g"
        )
        self.assertEqual(
            len(vat_transactions),
            2
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
                "NL"
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

    # CORRECT USAGE
    # Each line contains goods only
    def test_create_journal_with_vat_only_and_no_goods(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": 120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 0,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 120
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": 0,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -120
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            'nj',
        )
        self.assertEqual(
            header.ref,
            self.ref,
        )
        self.assertEqual(
            header.period,
            self.period
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
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        debit = lines[0]
        credit = lines[1]
        # DEBIT
        self.assertEqual(
            debit.description,
            self.description
        )
        self.assertEqual(
            debit.goods,
            0
        )
        self.assertEqual(
            debit.nominal,
            self.bank_nominal
        )
        self.assertEqual(
            debit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            debit.vat,
            120
        )
        self.assertEqual(
            debit.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            debit.vat_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            debit.vat_transaction,
            vat_transactions[0]
        )
        # CREDIT
        self.assertEqual(
            credit.description,
            self.description
        )
        self.assertEqual(
            credit.goods,
            0
        )
        self.assertEqual(
            credit.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            credit.vat_code,
            self.vat_code
        )
        self.assertEqual(
            credit.vat,
            -120
        )
        self.assertEqual(
            credit.goods_nominal_transaction,
            None
        )
        self.assertEqual(
            credit.vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            credit.vat_transaction,
            vat_transactions[1]
        )
        self.assertEqual(
            len(nominal_transactions),
            2
        )
        # debit goods
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            debit.pk
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            120
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[0].field,
            "v"
        )
        # credit goods
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            credit.pk
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            -120
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            self.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[1].field,
            "v"
        )

        self.assertEqual(
            len(vat_transactions),
            2
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
                "NL"
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

    # INCORRECT USAGE

    def test_create_journal_without_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": '',
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 20
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -20
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        header = NominalHeader.objects.all()
        lines = NominalLine.objects.all()
        self.assertEqual(
            len(header),
            0
        )
        self.assertEqual(
            len(lines),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">No total entered.  This should be the total value of the debit side of the journal i.e. the total of the positive values</li>',
            html=True
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_create_journal_where_debits_do_not_equal_total_entered(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": 120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 20
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": -50,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -10
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        header = NominalHeader.objects.all()
        lines = NominalLine.objects.all()
        self.assertEqual(
            len(header),
            0
        )
        self.assertEqual(
            len(lines),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">Debits and credits must total zero.  Total debits entered i.e. '
            'positives values entered is 120.00, and total credits entered i.e. negative values entered, is -60.00.  This gives a non-zero total of 60.00</li>',
            html=True
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_create_journal_without_header_total_and_no_analysis(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": '',
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        header = NominalHeader.objects.all()
        lines = NominalLine.objects.all()
        self.assertEqual(
            len(header),
            0
        )
        self.assertEqual(
            len(lines),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">No total entered.  This should be the total value of the debit side of the journal i.e. the total of the positive values</li>',
            html=True
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_create_journal_with_header_total_and_no_analysis(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": 120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        header = NominalHeader.objects.all()
        lines = NominalLine.objects.all()
        self.assertEqual(
            len(header),
            0
        )
        self.assertEqual(
            len(lines),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">The total of the debits does not equal the total you entered.</li>',
            html=True
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    # INCORRECT USAGE
    def test_create_journal_with_header_which_is_credit_total(self):
        self.client.force_login(self.user)
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "nj",
                "ref": self.ref,
                "date": self.date,
                "total": -120,
                "period": self.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data.update(line_data)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        header = NominalHeader.objects.all()
        lines = NominalLine.objects.all()
        self.assertEqual(
            len(header),
            0
        )
        self.assertEqual(
            len(lines),
            0
        )
        self.assertContains(
            response,
            '<li class="py-1">The total of the debits does not equal the total you entered.</li>',
            html=True
        )
        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )


class EditJournal(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.ref = "test journal"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))
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

    # CORRECT USAGE
    # Can request create journal view t=nj GET parameter
    def test_get_request_with_query_parameter(self):
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

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        lines = NominalLine.objects.all()

        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )

        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )

        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(nominal_transactions),
            4
        )

        # DEBITS

        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[1].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDITS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
        )

        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # This HTML fragment is before the selectize widget does its thing
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" disabled required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="nj" selected="selected">Journal</option>'
            '</select>',
            html=True
        )

    # CORRECT USAGE
    # JUST HALF THE GOODS AND VAT
    def test_edit_journal(self):
        self.client.force_login(self.user)

        header, line, nominal_transactions = create_nominal_journal({
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

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        lines = NominalLine.objects.all()
        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )

        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )

        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
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
                "NL"
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

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 60,
                "period": header.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 50,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 10
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -50,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -10
            }
        )
        line_forms[1]["id"] = lines[1].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 2
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # POST EDIT ...

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            60
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            50
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            10
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )
        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -50
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -10
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )
        # DEBIT NOM TRANS

        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
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
                "NL"
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

    # CORRECT USAGE

    def test_edit_journal_by_adding_two_new_lines(self):
        self.client.force_login(self.user)
        header, line, nominal_transactions = create_nominal_journal({
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
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        lines = NominalLine.objects.all()
        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )
        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )
        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
        )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 240,
                "period": header.period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 100,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -20
            }
        )
        line_forms[1]["id"] = lines[1].pk
        # NEW LINES
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 100,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 20
            }
        )
        line_forms[2]["id"] = ""
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -20
            }
        )
        line_forms[3]["id"] = ""
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 2
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # POST EDIT ...

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            240
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            4
        )
        lines = NominalLine.objects.all().order_by("pk")
        nominal_transactions = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            4
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )
        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )
        # NEW LINES
        self.assertEqual(
            lines[2].description,
            "line 1"
        )
        self.assertEqual(
            lines[2].goods,
            100
        )
        self.assertEqual(
            lines[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[2].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[2].vat,
            20
        )
        self.assertEqual(
            lines[2].goods_nominal_transaction,
            nominal_transactions[4]
        )
        self.assertEqual(
            lines[2].vat_nominal_transaction,
            nominal_transactions[5]
        )
        self.assertEqual(
            lines[2].vat_transaction,
            vat_transactions[2]
        )

        self.assertEqual(
            lines[3].description,
            "line 2"
        )
        self.assertEqual(
            lines[3].goods,
            -100
        )
        self.assertEqual(
            lines[3].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[3].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[3].vat,
            -20
        )
        self.assertEqual(
            lines[3].goods_nominal_transaction,
            nominal_transactions[6]
        )
        self.assertEqual(
            lines[3].vat_nominal_transaction,
            nominal_transactions[7]
        )
        self.assertEqual(
            lines[3].vat_transaction,
            vat_transactions[3]
        )
        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            8
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[0].field,
            "g"
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[1].field,
            "v"
        )

        self.assertEqual(
            nominal_transactions[4].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[4].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[4].line,
            lines[2].pk,
        )
        self.assertEqual(
            nominal_transactions[4].nominal,
            lines[2].nominal
        )
        self.assertEqual(
            nominal_transactions[4].value,
            lines[2].goods
        )
        self.assertEqual(
            nominal_transactions[4].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[4].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[4].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[4].field,
            "g"
        )

        self.assertEqual(
            nominal_transactions[5].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[5].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[5].line,
            lines[2].pk,
        )
        self.assertEqual(
            nominal_transactions[5].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[5].value,
            lines[2].vat
        )
        self.assertEqual(
            nominal_transactions[5].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[5].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[5].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[5].field,
            "v"
        )

        # CREDIT NOM TRANS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[2].field,
            "g"
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[6].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[6].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[6].line,
            lines[3].pk,
        )
        self.assertEqual(
            nominal_transactions[6].nominal,
            lines[3].nominal
        )
        self.assertEqual(
            nominal_transactions[6].value,
            lines[3].goods
        )
        self.assertEqual(
            nominal_transactions[6].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[6].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[6].type,
            header.type
        )
        self.assertEqual(
            nominal_transactions[6].field,
            "g"
        )

        self.assertEqual(
            nominal_transactions[7].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[7].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[7].line,
            lines[3].pk,
        )
        self.assertEqual(
            nominal_transactions[7].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[7].value,
            lines[3].vat
        )
        self.assertEqual(
            nominal_transactions[7].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[7].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[7].type,
            header.type
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
                "NL"
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

    # INCORRECT USAGE
    # START OFF WITH FOUR LINES AND THEN ZERO OUT BOTTOM TWO

    def test_edit_journal_by_zeroing_out_bottom_two_lines(self):
        self.client.force_login(self.user)

        header, line, nominal_transactions = create_nominal_journal({
            "header": {
                "type": "nj",
                "ref": "test journal",
                "period": self.period,
                "date": self.model_date,
                "total": 240,
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
                },
                {
                    "line_no": 3,
                    "description": "line 3",
                    "goods": 100,
                    "nominal": self.bank_nominal,
                    "vat_code": self.vat_code,
                    "vat": 20
                },
                {
                    "line_no": 4,
                    "description": "line 4",
                    "goods": -100,
                    "nominal": self.debtors_nominal,
                    "vat_code": self.vat_code,
                    "vat": -20
                }
            ],
        },
            self.vat_nominal
        )

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            240
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )

        # NOM LINES
        lines = NominalLine.objects.all().order_by("pk")
        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            4
        )
        nominal_transactions = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            4
        )
        debit_nom_trans = list(
            nominal_transactions[:2]) + list(nominal_transactions[4:6])
        debit_vat_trans = [vat_transactions[0], vat_transactions[2]]
        debit_lines = lines[::2]
        for i, line in enumerate(debit_lines):
            self.assertEqual(
                line.line_no,
                (2 * i) + 1
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.bank_nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                debit_nom_trans[(2 * i) + 0]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                debit_nom_trans[(2 * i) + 1]
            )
            self.assertEqual(
                line.vat_transaction,
                debit_vat_trans[i]
            )

        credit_nom_trans = list(
            nominal_transactions[2:4]) + list(nominal_transactions[6:])
        credit_vat_trans = [vat_transactions[1], vat_transactions[3]]
        credit_lines = lines[1::2]
        for i, line in enumerate(credit_lines):
            self.assertEqual(
                line.line_no,
                (2 * i) + 2
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.nominal,
                self.debtors_nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                credit_nom_trans[(2 * i) + 0]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                credit_nom_trans[(2 * i) + 1]
            )
            self.assertEqual(
                line.vat_transaction,
                credit_vat_trans[i]
            )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 240,
                "period": header.period.pk,
                "vat_type": header.vat_type
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 100,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -20
            }
        )
        line_forms[1]["id"] = lines[1].pk
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 0,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 0
            }
        )
        line_forms[2]["id"] = lines[2].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": 0,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": 0
            }
        )
        line_forms[3]["id"] = lines[3].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 4
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<li class="py-1">Goods and Vat cannot both be zero.</li>',
            html=True
        )

    # CORRECT USAGE
    # START OFF WITH FOUR LINES AND THEN MARK BOTTOM TWO AS DELETED
    def test_edit_journal_by_deleting_bottom_two_lines(self):
        self.client.force_login(self.user)
        header, line, nominal_transactions = create_nominal_journal({
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
                },
                {
                    "line_no": 3,
                    "description": "line 3",
                    "goods": 100,
                    "nominal": self.bank_nominal,
                    "vat_code": self.vat_code,
                    "vat": 20
                },
                {
                    "line_no": 4,
                    "description": "line 4",
                    "goods": -100,
                    "nominal": self.debtors_nominal,
                    "vat_code": self.vat_code,
                    "vat": -20
                }
            ],
        },
            self.vat_nominal
        )

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )

        # NOM LINES
        lines = NominalLine.objects.all().order_by("pk")
        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()

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
                "NL"
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
            len(vat_transactions),
            4
        )
        nominal_transactions = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            4
        )

        debit_nom_trans = list(
            nominal_transactions[:2]) + list(nominal_transactions[4:6])
        debit_vat_trans = [ vat_transactions[0], vat_transactions[2] ]
        debit_lines = lines[::2]
        for i, line in enumerate(debit_lines):
            self.assertEqual(
                line.line_no,
                (2 * i) + 1
            )
            self.assertEqual(
                line.goods,
                100
            )
            self.assertEqual(
                line.nominal,
                self.bank_nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                debit_nom_trans[(2 * i) + 0]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                debit_nom_trans[(2 * i) + 1]
            )
            self.assertEqual(
                line.vat_transaction,
                debit_vat_trans[i]
            )

        credit_nom_trans = list(
            nominal_transactions[2:4]) + list(nominal_transactions[6:])
        credit_vat_trans = [ vat_transactions[1], vat_transactions[3] ]
        credit_lines = lines[1::2]
        for i, line in enumerate(credit_lines):
            self.assertEqual(
                line.line_no,
                (2 * i) + 2
            )
            self.assertEqual(
                line.goods,
                -100
            )
            self.assertEqual(
                line.nominal,
                self.debtors_nominal
            )
            self.assertEqual(
                line.vat_code,
                self.vat_code
            )
            self.assertEqual(
                line.vat,
                -20
            )
            self.assertEqual(
                line.goods_nominal_transaction,
                credit_nom_trans[(2 * i) + 0]
            )
            self.assertEqual(
                line.vat_nominal_transaction,
                credit_nom_trans[(2 * i) + 1]
            )
            self.assertEqual(
                line.vat_transaction,
                credit_vat_trans[i]
            )

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 120,
                "period": header.period.pk,
                "vat_type": header.vat_type
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 100,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -20
            }
        )
        line_forms[1]["id"] = lines[1].pk
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 0,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 0
            }
        )
        line_forms[2]["id"] = lines[2].pk
        line_forms[2]["DELETE"] = "yes"
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": 0,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": 0
            }
        )
        line_forms[3]["id"] = lines[3].pk
        line_forms[3]["DELETE"] = "yes"
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 4
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # POST EDIT ...
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )

        # NOM LINES
        lines = NominalLine.objects.all().order_by("pk")
        vat_transactions = VatTransaction.objects.all().order_by("line")
        self.assertEqual(
            len(vat_transactions),
            2
        )
        nominal_transactions = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )

        self.assertEqual(
            len(nominal_transactions),
            4
        )

        debit_nom_trans = nominal_transactions[:2]
        debit_line = lines[0]
        self.assertEqual(
            debit_line.line_no,
            1
        )
        self.assertEqual(
            debit_line.goods,
            100
        )
        self.assertEqual(
            debit_line.nominal,
            self.bank_nominal
        )
        self.assertEqual(
            debit_line.vat_code,
            self.vat_code
        )
        self.assertEqual(
            debit_line.vat,
            20
        )
        self.assertEqual(
            debit_line.goods_nominal_transaction,
            debit_nom_trans[0]
        )
        self.assertEqual(
            debit_line.vat_nominal_transaction,
            debit_nom_trans[1]
        )
        self.assertEqual(
            debit_line.vat_transaction,
            vat_transactions[0]
        )

        credit_nom_trans = nominal_transactions[2:]
        credit_line = lines[1]
        self.assertEqual(
            credit_line.line_no,
            2
        )
        self.assertEqual(
            credit_line.goods,
            -100
        )
        self.assertEqual(
            credit_line.nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            credit_line.vat_code,
            self.vat_code
        )
        self.assertEqual(
            credit_line.vat,
            -20
        )
        self.assertEqual(
            credit_line.goods_nominal_transaction,
            credit_nom_trans[0]
        )
        self.assertEqual(
            credit_line.vat_nominal_transaction,
            credit_nom_trans[1]
        )
        self.assertEqual(
            credit_line.vat_transaction,
            vat_transactions[1]
        )

        total = 0
        for tran in nominal_transactions:
            total = total + tran.value
        self.assertEqual(total, 0)

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
                "NL"
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

    def test_edit_header_only(self):
        """
        A change in the header only might still mean the lines and nominal and vat transactions need updating
        E.g. the period is changed.
        """

        self.client.force_login(self.user)

        header, line, nominal_transactions = create_nominal_journal({
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

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        lines = NominalLine.objects.all()
        create_vat_transactions(header, lines)
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )

        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )

        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS
        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
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
                "NL"
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

        new_period = Period.objects.create(fy=self.fy, fy_and_period="202002", period="02", month_end=date(2020,2,29))

        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": header.type,
                "ref": header.ref,
                "date": header.date.strftime(DATE_INPUT_FORMAT),
                "total": 120,
                "period": new_period.pk,
                "vat_type": "o"
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 100,
                "nominal": lines[0].nominal_id,
                "vat_code": lines[0].vat_code_id,
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": lines[1].vat_code_id,
                "vat": -20
            }
        )
        line_forms[1]["id"] = lines[1].pk
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 2
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # POST EDIT ...
        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            new_period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.vat_type,
            "o"
        )
        # NOM LINES
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            2
        )
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )
        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )
        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            new_period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            new_period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS
        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            new_period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            new_period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
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
                "NL"
            )
            self.assertEqual(
                vat_tran.ref,
                header.ref
            )
            self.assertEqual(
                vat_tran.period,
                new_period
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


class VoidJournal(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
        cls.ref = "test journal"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_end=date(2020,1,31))
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

    # INCORRECT USAGE

    def test_void_journal_already_voided(self):
        self.client.force_login(self.user)

        header, line = create_nominal_journal_without_nom_trans({
            "header": {
                "type": "nj",
                "ref": "test journal",
                "period": self.period,
                "date": self.model_date,
                "total": 120,
                "status": "v",
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
        )

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.status,
            'v'
        )

        # NOM LINES

        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(nominal_transactions),
            0
        )
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
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
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
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

        data = {}
        data["void-id"] = header.id
        url = reverse("nominals:void", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            False
        )

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.status,
            'v'
        )

        # NOM LINES

        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
        self.assertEqual(
            len(nominal_transactions),
            0
        )
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
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
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
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

    # CORRECT USAGE
    # JUST HALF THE GOODS AND VAT
    def test_void_journal(self):
        self.client.force_login(self.user)

        header, line, nominal_transactions = create_nominal_journal({
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

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.status,
            'c'
        )

        # NOM LINES

        lines = NominalLine.objects.all()

        create_vat_transactions(header, lines)

        vat_transactions = VatTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(vat_transactions),
            2
        )
        nominal_transactions = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )

        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nominal_transactions[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nominal_transactions[1]
        )
        self.assertEqual(
            lines[0].vat_transaction,
            vat_transactions[0]
        )

        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nominal_transactions[2]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nominal_transactions[3]
        )
        self.assertEqual(
            lines[1].vat_transaction,
            vat_transactions[1]
        )

        # DEBIT NOM TRANS
        self.assertEqual(
            len(nominal_transactions),
            4
        )
        self.assertEqual(
            nominal_transactions[0].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[0].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[0].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[0].nominal,
            lines[0].nominal
        )
        self.assertEqual(
            nominal_transactions[0].value,
            lines[0].goods
        )
        self.assertEqual(
            nominal_transactions[0].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[0].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[0].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[1].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[1].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[1].line,
            lines[0].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[0].vat
        )
        self.assertEqual(
            nominal_transactions[1].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[1].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[1].type,
            header.type
        )

        # CREDIT NOM TRANS

        self.assertEqual(
            nominal_transactions[2].module,
            "NL",
        )
        self.assertEqual(
            nominal_transactions[2].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[2].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[2].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[2].value,
            lines[1].goods
        )
        self.assertEqual(
            nominal_transactions[2].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[2].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[2].type,
            header.type
        )

        self.assertEqual(
            nominal_transactions[3].module,
            "NL"
        )
        self.assertEqual(
            nominal_transactions[3].header,
            header.pk
        )
        self.assertEqual(
            nominal_transactions[3].line,
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[3].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nominal_transactions[3].value,
            lines[1].vat
        )
        self.assertEqual(
            nominal_transactions[3].ref,
            header.ref
        )
        self.assertEqual(
            nominal_transactions[3].period,
            header.period
        )
        self.assertEqual(
            nominal_transactions[3].type,
            header.type
        )

        data = {}
        data["void-id"] = header.id
        url = reverse("nominals:void", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("nominals:transaction_enquiry")
        )

        # POST VOID

        header = NominalHeader.objects.all()
        self.assertEqual(
            len(header),
            1
        )
        header = header[0]
        self.assertEqual(
            header.type,
            "nj"
        )
        self.assertEqual(
            header.ref,
            "test journal"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.total,
            120
        )
        self.assertEqual(
            header.status,
            'v'
        )

        # NOM LINES

        lines = NominalLine.objects.all()
        self.assertEqual(
            len(lines),
            2
        )
        self.assertEqual(
            lines[0].description,
            "line 1"
        )
        self.assertEqual(
            lines[0].goods,
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
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
            lines[0].vat_transaction,
            None
        )

        self.assertEqual(
            lines[1].description,
            "line 2"
        )
        self.assertEqual(
            lines[1].goods,
            -100
        )
        self.assertEqual(
            lines[1].nominal,
            self.debtors_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
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
            lines[1].vat_transaction,
            None
        )

        self.assertEqual(
            len(NominalTransaction.objects.all()),
            0
        )


        self.assertEqual(
            len(
                VatTransaction.objects.all()
            ),
            0
        )

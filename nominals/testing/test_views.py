from datetime import datetime, timedelta
from itertools import chain

from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accountancy.testing.helpers import create_formset_data, create_header
from nominals.models import Nominal
from utils.helpers import sort_multiple
from vat.models import Vat

from ..models import NominalHeader, NominalLine, NominalTransaction
from .helpers import create_nominal_journal

"""
These tests just check that the nominal module uses the accountancy general classes correctly.
The testing of these general classes is done in the purchase ledger.
"""

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
MATCHING_FORM_PREFIX = "match"
PERIOD = '202007' # the calendar month i made the change !

class CreateJournal(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.factory = RequestFactory()
        cls.ref = "test journal"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.description = "a line description"
        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.debtors_nominal = Nominal.objects.create(parent=current_assets, name="Trade Debtors")
        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(parent=current_assets, name="Vat")

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)
        cls.url = reverse("nominals:create")

    # CORRECT USAGE
    # Can request create journal view t=nj GET parameter
    def test_get_request_with_query_parameter(self):
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
    def test_create_journal(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "period": PERIOD
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
            PERIOD
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
        lines = NominalLine.objects.all()
        nominal_transactions = NominalTransaction.objects.all()
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
            PERIOD
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
            PERIOD
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
            PERIOD
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
            PERIOD
        )
        self.assertEqual(
            nominal_transactions[3].type,
            "nj"
        )
        self.assertEqual(
            nominal_transactions[3].field,
            "v"
        )

    # INCORRECT USAGE
    def test_create_journal_without_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": '',
            "period": PERIOD
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

    # INCORRECT USAGE
    def test_create_journal_where_debits_do_not_equal_total_entered(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "period": PERIOD
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
            'positives values entered is 120, and total credits entered i.e. negative values entered, is -60.  This gives a non-zero total of 60</li>',
            html=True
        )

    # INCORRECT USAGE
    def test_create_journal_without_header_total_and_no_analysis(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": '',
            "period": PERIOD
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

    # INCORRECT USAGE
    def test_create_journal_with_header_total_and_no_analysis(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "period": PERIOD
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


    # INCORRECT USAGE
    def test_create_journal_with_header_which_is_credit_total(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "period": PERIOD
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



class EditJournal(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.ref = "test journal"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')

        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.debtors_nominal = Nominal.objects.create(parent=current_assets, name="Trade Debtors")

        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(parent=current_assets, name="Vat")

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

    # CORRECT USAGE
    # Can request create journal view t=nj GET parameter
    def test_get_request_with_query_parameter(self):

        header, line, nominal_transactions = create_nominal_journal({
            "header": {
                "type": "nj",
                "ref": "test journal",
                "period": PERIOD,
                "date": timezone.now(),
                "total": 120
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
            PERIOD
        )
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
            2
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
            lines[1].pk,
        )
        self.assertEqual(
            nominal_transactions[1].nominal,
            lines[1].nominal
        )
        self.assertEqual(
            nominal_transactions[1].value,
            lines[1].goods
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

        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.get(url)
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
    def test_edit_journal(self):

        header, line, nominal_transactions = create_nominal_journal({
            "header": {
                "type": "nj",
                "ref": "test journal",
                "period": PERIOD,
                "date": timezone.now(),
                "total": 120
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
            PERIOD
        )

        # NOM LINES

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
            "date": header.date,
            "total": 60,
            "period": header.period
            }
        )
        data.update(header_data)
        line_forms = []
        line_forms.append(
            {
                "description": lines[0].description,
                "goods": 50,
                "nominal": lines[0].nominal,
                "vat_code": lines[0].vat_code,
                "vat": 10
            }
        )
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -50,
                "nominal": lines[1].nominal,
                "vat_code": lines[1].vat_code,
                "vat": -10
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["LINE-INITIAL-FORMS"] = 2
        data.update(line_data)
        url = reverse("nominals:edit", kwargs={"pk": header.pk})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
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

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
match_form_prefix = "match"
DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

class LineChanges(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(username="dummy", password="dummy")
        cls.ref = "test journal"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
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

    def test_vat_code_changed_to_no_vat_code(self):
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

        new_period = Period.objects.create(fy=self.fy, fy_and_period="202002", period="02", month_start=date(2020,2,29))

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
                "vat_code": '',
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": '',
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
            0
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
            None
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
            None
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
            None
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


    def test_no_vat_code_changed_to_vat_code(self):
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
                    "vat_code": None,
                    "vat": 20
                },
                {
                    "line_no": 2,
                    "description": "line 2",
                    "goods": -100,
                    "nominal": self.debtors_nominal,
                    "vat_code": None,
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
        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
            0
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
            None
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
            None
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
            None
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

        new_period = Period.objects.create(fy=self.fy, fy_and_period="202002", period="02", month_start=date(2020,2,29))

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
                "vat_code": self.vat_code.pk,
                "vat": 20
            }
        )
        line_forms[0]["id"] = lines[0].pk
        line_forms.append(
            {
                "description": lines[1].description,
                "goods": -100,
                "nominal": lines[1].nominal_id,
                "vat_code": self.vat_code.pk,
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
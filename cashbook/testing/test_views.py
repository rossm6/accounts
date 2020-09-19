from json import loads

from datetime import datetime

from django.shortcuts import reverse
from django.test import TestCase

from cashbook.models import (CashBook, CashBookHeader, CashBookLine,
                             CashBookTransaction)
from nominals.models import Nominal, NominalTransaction
from accountancy.testing.helpers import *
from accountancy.helpers import sort_multiple
from vat.models import Vat

HEADER_FORM_PREFIX = 'header'
LINE_FORM_PREFIX = 'line'


def create_lines(line_cls, header, lines):
    tmp = []
    for i, line in enumerate(lines):
        line["line_no"] = i + 1
        line["header"] = header
        tmp.append(line_cls(**line))
    return line_cls.objects.bulk_create(tmp)


def create_nom_trans(nom_tran_cls, line_cls, header, lines, bank_nominal, vat_nominal):
    nom_trans = []
    for line in lines:
        if line.goods:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value= -1 * line.goods,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="g",
                    type=header.type
                )
            )
        if line.vat:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value= -1 * line.vat,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="v",
                    type=header.type
                )
            )
        if line.goods or line.vat:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=bank_nominal,
                    value=line.goods + line.vat,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="t",
                    type=header.type
                )
            )
    nom_trans = NominalTransaction.objects.bulk_create(nom_trans)
    nom_trans = sort_multiple(nom_trans, *[(lambda n: n.line, False)])
    goods_and_vat = nom_trans[:-1]
    for i, line in enumerate(lines):
        line.goods_nominal_transaction = nom_trans[3 * i]
        line.vat_nominal_transaction = nom_trans[(3 * i) + 1]
        line.total_nominal_transaction = nom_trans[(3 * i) + 2]
    line_cls.objects.bulk_update(
        lines,
        ["goods_nominal_transaction", "vat_nominal_transaction",
            "total_nominal_transaction"]
    )


def create_cash_book_trans(cash_book_tran_cls, header):
    cash_book_tran_cls.objects.create(
        module="CB",
        header=header.pk,
        line=1,
        value=header.total,
        ref=header.ref,
        period=header.period,
        date=header.date,
        field="t",
        cash_book=header.cash_book,
        type=header.type
    )


class CreatePayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

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

    def test_get_request_without_query_params(self):
        response = self.client.get(reverse("cashbook:create"))
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp">Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp" selected>Payment</option>'
            '<option value="cr">Receipt</option>'
            '</select>',
            html=True
        )

    def test_get_request_with_query_param(self):
        response = self.client.get(reverse("cashbook:create") + "?t=cp")
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp">Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp" selected>Payment</option>'
            '<option value="cr">Receipt</option>'
            '</select>',
            html=True
        )

    def test_create_single_line_POSITIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cp",
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
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cp",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 0
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cp",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 240
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            6
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )

        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            100
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            20
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[4].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            -120
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cp",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cp",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -240
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.not_bank_nominal
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
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            100
        )
        self.assertEqual(
            lines[1].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            6
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )

        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            -100
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            -20
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[4].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            120
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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


class EditPayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

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

    def test_get_request(self):

        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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

        response = self.client.get(reverse("cashbook:edit", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required disabled id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp">Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp" selected>Payment</option>'
            '<option value="cr">Receipt</option>'
            '</select>',
            html=True
        )


    def test_edit_single_line_POSITIVE(self):
        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": 240
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            200
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            40
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -240
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": 360
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 100,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": 200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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
            6
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nom_trans[3]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nom_trans[4]
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            nom_trans[5]
        )


        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )


        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            200
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            40
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            -240
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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
        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": -240
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -200
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -40
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            240
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": -360
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -100,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": -200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            6
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nom_trans[3]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nom_trans[4]
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            nom_trans[5]
        )


        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )


        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            -200
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            -40
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            240
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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
        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
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
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -20,
                "DELETE": "yes"
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": -200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -40,
                "DELETE": "yes"
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<li class="py-1">Cash book transactions cannot be for a zero value.</li>',
            html=True
        )


class CreateRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

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

        cls.url = reverse("cashbook:create") + "?t=cr"

    def test_get_request_without_query_params(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp">Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp">Payment</option>'
            '<option value="cr" selected>Receipt</option>'
            '</select>',
            html=True
        )


    def test_create_single_line_POSITIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cr",
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
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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

    # INCORRECT USAGE
    def test_create_zero_payment_with_no_lines(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cr",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 0
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
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cr",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": 240
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            100
        )
        self.assertEqual(
            lines[0].nominal,
            self.not_bank_nominal
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
            self.description
        )
        self.assertEqual(
            lines[1].goods,
            100
        )
        self.assertEqual(
            lines[1].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            6
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )

        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            -100
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            -20
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[4].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            120
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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

    
    def test_create_single_line_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cr",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -120
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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


    def test_create_with_two_lines_NEGATIVE(self):
        data = {}
        header_data = create_header(
            HEADER_FORM_PREFIX,
            {
                "type": "cr",
                "cash_book": self.cash_book.pk,
                "ref": self.ref,
                "date": self.date,
                "total": -240
            }
        )
        data.update(header_data)
        line_forms = [
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.not_bank_nominal.pk,
                "vat_code": self.vat_code.pk,
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

        lines = CashBookLine.objects.all()
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -20
        )

        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            6
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )

        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            100
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            20
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[4].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            -120
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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


class EditRefund(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

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

    def test_get_request(self):

        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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

        response = self.client.get(reverse("cashbook:edit", kwargs={"pk": header.pk}))
        self.assertEqual(
            response.status_code,
            200
        )

        self.assertContains(
            response,
            '<select name="header-type" class="transaction-type-select" required disabled id="id_header-type">'
            '<option value="">---------</option>'
            '<option value="cbp">Brought Forward Payment</option>'
            '<option value="cbr">Brought Forward Receipt</option>'
            '<option value="cp">Payment</option>'
            '<option value="cr" selected>Receipt</option>'
            '</select>',
            html=True
        )


    def test_edit_single_line_POSITIVE(self):
        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": 240
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -200
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -40
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            240
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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


    def test_create_new_line(self):
        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": 360
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 100,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": 200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all().order_by("pk")
        self.assertEqual(
            len(lines),
            2
        )
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            6
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nom_trans[3]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nom_trans[4]
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            nom_trans[5]
        )


        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )


        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            -200
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            -40
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            240
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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


    def test_edit_single_line_NEGATIVE(self):
        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": -240
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -40
            }
        ]
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -40
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            200
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            40
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -240
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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


    def test_create_new_line_NEGATIVE(self):
        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": -360
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": -100,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -20
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": -200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": -40
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
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
            6
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[1].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[1].vat,
            -40
        )
        self.assertEqual(
            lines[1].goods_nominal_transaction,
            nom_trans[3]
        )
        self.assertEqual(
            lines[1].vat_nominal_transaction,
            nom_trans[4]
        )
        self.assertEqual(
            lines[1].total_nominal_transaction,
            nom_trans[5]
        )


        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
        )


        self.assertEqual(
            nom_trans[3].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[3].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[3].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[3].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[3].value,
            200
        )
        self.assertEqual(
            nom_trans[3].field,
            'g'
        )
        self.assertEqual(
            nom_trans[3].type,
            header.type
        )

        self.assertEqual(
            nom_trans[4].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[4].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[4].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[4].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[4].value,
            40
        )
        self.assertEqual(
            nom_trans[4].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[5].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[5].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[5].line,
            lines[1].pk
        )
        self.assertEqual(
            nom_trans[5].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[5].value,
            -240
        )
        self.assertEqual(
            nom_trans[5].field,
            't'
        )
        self.assertEqual(
            nom_trans[5].type,
            header.type
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

    def test_cannot_edit_to_zero(self):
        header = CashBookHeader.objects.create(**{
            "type": "cr",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "goods": 100,
            "vat": 20
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

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
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
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            -100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            -20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
                "cash_book": header.cash_book.pk,
                "ref": header.ref,
                "date": header.date,
                "total": 0
            }
        )
        data.update(header_data)
        line = lines[0]
        line_forms = [
            {
                "id": line.pk,
                "description": line.description,
                "goods": 100,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 20,
                "DELETE": "yes"
            }
        ]
        line_forms.append(
            {
                "description": line.description,
                "goods": 200,
                "nominal": line.nominal_id,
                "vat_code": line.vat_code_id,
                "vat": 40,
                "DELETE": "yes"
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 1
        data.update(line_data)
        response = self.client.post(reverse("cashbook:edit", kwargs={"pk": header.pk}), data)
        self.assertEqual(
            response.status_code,
            200
        )
        self.assertContains(
            response,
            '<li class="py-1">Cash book transactions cannot be for a zero value.</li>',
            html=True
        )


class VoidTransaction(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

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

    def test_void(self):

        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
            "total": -120,
            "goods": -100,
            "vat": -20
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
            header.status,
            'c'
        )

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )
        nom_trans = NominalTransaction.objects.all()
        self.assertEqual(
            len(nom_trans),
            3
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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
        )
        self.assertEqual(
            lines[0].vat,
            -20
        )
        self.assertEqual(
            lines[0].goods_nominal_transaction,
            nom_trans[0]
        )
        self.assertEqual(
            lines[0].vat_nominal_transaction,
            nom_trans[1]
        )
        self.assertEqual(
            lines[0].total_nominal_transaction,
            nom_trans[2]
        )

        self.assertEqual(
            nom_trans[0].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[0].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[0].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[0].nominal,
            self.not_bank_nominal
        )
        self.assertEqual(
            nom_trans[0].value,
            100
        )
        self.assertEqual(
            nom_trans[0].field,
            'g'
        )
        self.assertEqual(
            nom_trans[0].type,
            header.type
        )

        self.assertEqual(
            nom_trans[1].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[1].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[1].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[1].nominal,
            self.vat_nominal
        )
        self.assertEqual(
            nom_trans[1].value,
            20
        )
        self.assertEqual(
            nom_trans[1].field,
            'v'
        )
        self.assertEqual(
            nom_trans[1].type,
            header.type
        )

        self.assertEqual(
            nom_trans[2].module,
            'CB'
        )
        self.assertEqual(
            nom_trans[2].header,
            header.pk
        )
        self.assertEqual(
            nom_trans[2].line,
            lines[0].pk
        )
        self.assertEqual(
            nom_trans[2].nominal,
            self.bank_nominal
        )
        self.assertEqual(
            nom_trans[2].value,
            -120
        )
        self.assertEqual(
            nom_trans[2].field,
            't'
        )
        self.assertEqual(
            nom_trans[2].type,
            header.type
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
        data["void-id"] = header.pk
        response = self.client.post(reverse("cashbook:void"), data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf")
        json_content = loads(content)
        self.assertEqual(
            json_content["success"],
            True
        )
        self.assertEqual(
            json_content["href"],
            reverse("cashbook:transaction_enquiry")
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
            header.status,
            'v'
        )

        lines = CashBookLine.objects.all()
        self.assertEqual(
            len(lines),
            1
        )

        ##

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
            self.not_bank_nominal
        )
        self.assertEqual(
            lines[0].vat_code,
            self.vat_code
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

        ##

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
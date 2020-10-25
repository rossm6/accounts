from datetime import datetime
from json import loads

from accountancy.helpers import sort_multiple
from accountancy.testing.helpers import *
from cashbook.helpers import *
from cashbook.models import (CashBook, CashBookHeader, CashBookLine,
                             CashBookTransaction)
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalTransaction
from vat.models import Vat, VatTransaction

HEADER_FORM_PREFIX = 'header'
LINE_FORM_PREFIX = 'line'


class VoidTransaction(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.user = get_user_model().objects.create_user(username="dummy", password="dummy")
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
        self.client.force_login(self.user)

        header = CashBookHeader.objects.create(**{
            "type": "cp",
            "cash_book": self.cash_book,
            "ref": self.ref,
            "date": self.date,
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

        vat_transactions = VatTransaction.objects.all()
        self.assertEqual(
            len(vat_transactions),
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
            lines[0].vat_transaction,
            vat_transactions[0]
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
        self.assertEqual(
            lines[0].vat_transaction,
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


        self.assertEqual(
            len(
                VatTransaction.objects.all()
            ),
            0
        )
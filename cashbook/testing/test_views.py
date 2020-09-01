from datetime import datetime

from django.shortcuts import reverse
from django.test import TestCase

from cashbook.models import (CashBook, CashBookHeader, CashBookLine,
                             CashBookTransaction)
from nominals.models import Nominal, NominalTransaction
from purchases.helpers import create_formset_data, create_header
from vat.models import Vat

HEADER_FORM_PREFIX = 'header' 
LINE_FORM_PREFIX = 'line'

class CreatePayment(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.description = "duh"
        cls.ref = "test"
        cls.date = datetime.now().strftime('%Y-%m-%d')

        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.not_bank_nominal = Nominal.objects.create(parent=current_assets, name="Not Bank Nominal")

        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(parent=liabilities, name="Current Liabilities")
        cls.purchase_control = Nominal.objects.create(parent=current_liabilities, name="Purchase Ledger Control")
        cls.vat_nominal = Nominal.objects.create(parent=current_liabilities, name="Vat")

        # Cash book
        cls.cash_book = CashBook.objects.create(name="Cash Book", nominal=cls.bank_nominal) # Bank Nominal

        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)

        cls.url = reverse("cashbook:create") + "?=cp"

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
        self.assertEqual(
            len(headers),
            1
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


        cash_book_trans = CashBookTransaction.objects.all()
        self.assertEqual(
            len(cash_book_trans),
            1
        )


    def test_create_with_two_lines_POSITIVE(self):
        pass


    def test_create_single_line_NEGATIVE(self):
        pass


    def test_create_with_two_lines_NEGATIVE(self):
        pass

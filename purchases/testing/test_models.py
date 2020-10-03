from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from items.models import Item
from nominals.models import Nominal
from vat.models import Vat

from ..helpers import create_lines, create_invoices
from ..models import PurchaseHeader, PurchaseLine, Supplier


class PurchaseLineModelTest(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d')        
        cls.item = Item.objects.create(code="aa", description="aa-aa")
        cls.description = "a line description"
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)    

    def test_ordering_is_by_ascending_line_no(self):
        invoice = create_invoices(self.supplier, "invoice", 1, 1000)[0]
        lines = []
        for i in range(10, 0, -1):
            lines.append(
                PurchaseLine(
                    header=invoice,
                    item=self.item,
                    description=self.description,
                    goods=100,
                    nominal=self.nominal,
                    vat_code=self.vat_code,
                    vat=20,
                    line_no=i
                )
            )
        PurchaseLine.objects.bulk_create(lines)
        lines = PurchaseLine.objects.all()
        self.assertEqual(len(lines), 10)
        for index, line in enumerate(lines):
            self.assertEqual(
                line.line_no,
                index + 1
            )
        
from datetime import date, datetime, timedelta

from controls.models import FinancialYear, Period
from django.test import TestCase
from django.utils import timezone
from nominals.models import Nominal
from vat.models import Vat

from ..helpers import create_invoices, create_lines
from ..models import PurchaseHeader, PurchaseLine, Supplier

DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

class PurchaseLineModelTest(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.supplier = Supplier.objects.create(name="test_supplier")
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
        current_assets = Nominal.objects.create(parent=assets, name="Current Assets")
        cls.nominal = Nominal.objects.create(parent=current_assets, name="Bank Account")
        cls.vat_code = Vat.objects.create(code="1", name="standard rate", rate=20)    

    def test_ordering_is_by_ascending_line_no(self):
        invoice = create_invoices(self.supplier, "invoice", 1, self.period, 1000)[0]
        lines = []
        for i in range(10, 0, -1):
            lines.append(
                PurchaseLine(
                    header=invoice,
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
        
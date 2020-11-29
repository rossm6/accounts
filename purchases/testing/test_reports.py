from datetime import date, datetime, timedelta

from controls.models import FinancialYear, Period
from django.test import RequestFactory, TestCase
from purchases.models import PurchaseHeader, PurchaseMatching, Supplier
from purchases.reports import creditors

DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

class CreditReport(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period_06 = Period.objects.create(fy=fy, period="01", fy_and_period="202006", month_end=date(2020,6,30))
        cls.period_07 = Period.objects.create(fy=fy, period="02", fy_and_period="202007", month_end=date(2020,7,31))
        cls.period_08 = Period.objects.create(fy=fy, period="03", fy_and_period="202008", month_end=date(2020,8,31))

    def test_transaction_not_matched_entered_before_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            1
        )
        self.assertEqual(
            outstanding_trans[0],
            invoice
        )
        self.assertEqual(
            outstanding_trans[0].due,
            120
        )

    def test_transaction_not_matched_entered_in_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_07,
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            1
        )
        self.assertEqual(
            outstanding_trans[0],
            invoice
        )
        self.assertEqual(
            outstanding_trans[0].due,
            120
        )

    def test_transaction_not_matched_entered_after_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_08,
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            0
        )

    def test_transaction_matched_to_one_other_before_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_06,
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": self.period_06
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            2
        )
        invoice_tran, payment_tran = outstanding_trans
        self.assertEqual(
            invoice_tran,
            invoice
        )
        self.assertEqual(
            invoice_tran.due,
            60
        )
        self.assertEqual(
            payment_tran,
            payment
        )
        self.assertEqual(
            payment.due,
            -60
        )

    def test_transaction_matched_to_one_other_in_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_07,
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": self.period_07
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            2
        )
        invoice_tran, payment_tran = outstanding_trans
        self.assertEqual(
            invoice_tran,
            invoice
        )
        self.assertEqual(
            invoice_tran.due,
            60
        )
        self.assertEqual(
            payment_tran,
            payment
        )
        self.assertEqual(
            payment.due,
            -60
        )

    def test_transaction_matched_to_one_other_after_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_08,
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": self.period_08
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            1
        )
        invoice_tran, *rest = outstanding_trans
        self.assertEqual(
            invoice_tran,
            invoice
        )
        self.assertEqual(
            invoice_tran.due,
            120
        )

    def test_transaction_matched_to_one_other_after_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_08,
                "due": -60,
                "paid": -60
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_07,
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_1,
                "matched_to": invoice,
                "value": 60,
                "period": self.period_08
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 60,
                "period": self.period_07
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            2
        )
        invoice_tran, payment_2_tran = outstanding_trans
        self.assertEqual(
            invoice_tran,
            invoice
        )
        self.assertEqual(
            invoice_tran.due,
            60
        )
        self.assertEqual(
            payment_2_tran,
            payment_2
        )
        self.assertEqual(
            payment_2_tran.due,
            -60
        )

    def test_invoice_and_payment_matched_via_zero_transaction_in_same_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_06,
                "due": 0,
                "paid": -120
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": self.period_07,
                "due": 0,
                "paid": 0
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 120,
                "period": self.period_07
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": payment_1,
                "value": -120,
                "period": self.period_07
            }
        )
        outstanding_trans = creditors(self.period_07)
        self.assertEqual(
            len(outstanding_trans),
            0
        )


    # SAME AS ABOVE EXCEPT THIS TIME THE REPORT IS RUN A self.period_07 PRIOR
    def test_invoice_and_payment_matched_via_zero_transaction(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": self.period_06,
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": self.period_06,
                "due": 0,
                "paid": -120
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": self.period_07,
                "due": 0,
                "paid": 0
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 120,
                "period": self.period_07
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": payment_1,
                "value": -120,
                "period": self.period_07
            }
        )
        outstanding_trans = creditors(self.period_06)
        self.assertEqual(
            len(outstanding_trans),
            2
        )
        invoice_tran, payment_1_tran = outstanding_trans
        self.assertEqual(
            invoice_tran,
            invoice
        )
        self.assertEqual(
            invoice_tran.due,
            120
        )
        self.assertEqual(
            payment_1_tran,
            payment_1
        )
        self.assertEqual(
            payment_1_tran.due,
            -120
        )


    def test_zero_value_transactions_are_excluded(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.model_date,
                "due_date": self.model_due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": self.period_06,
                "due": 0,
                "paid": 0
            }
        )
        outstanding_trans = creditors(self.period_06)
        self.assertEqual(
            len(outstanding_trans),
            0
        )

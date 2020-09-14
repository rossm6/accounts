from datetime import datetime, timedelta

from django.test import RequestFactory, TestCase

from purchases.models import PurchaseHeader, PurchaseMatching, Supplier
from purchases.reports import creditors

PERIOD = "202007"


class CreditReport(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(name="test_supplier")
        cls.ref = "test matching"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime('%Y-%m-%d')

    def test_transaction_not_matched_entered_before_period(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": '202006',
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": PERIOD,
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202008",
                "due": 120,
                "paid": 0
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202006",
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": "202006"
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202007",
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": "202007"
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 60,
                "paid": 60
            }
        )
        payment = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202008",
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment,
                "matched_to": invoice,
                "value": 60,
                "period": "202008"
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202008",
                "due": -60,
                "paid": -60
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202007",
                "due": -60,
                "paid": -60
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_1,
                "matched_to": invoice,
                "value": 60,
                "period": "202008"
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 60,
                "period": "202007"
            }
        )
        outstanding_trans = creditors(PERIOD)
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202006",
                "due": 0,
                "paid": -120
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": "202007",
                "due": 0,
                "paid": 0
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 120,
                "period": "202007"
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": payment_1,
                "value": -120,
                "period": "202007"
            }
        )
        outstanding_trans = creditors(PERIOD)
        self.assertEqual(
            len(outstanding_trans),
            0
        )


    # SAME AS ABOVE EXCEPT THIS TIME THE REPORT IS RUN A PERIOD PRIOR
    def test_invoice_and_payment_matched_via_zero_transaction(self):
        invoice = PurchaseHeader.objects.create(
            **{
                "type": "pi",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": 100,
                "vat": 20,
                "total": 120,
                "period": "202006",
                "due": 0,
                "paid": 120
            }
        )
        payment_1 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": -100,
                "vat": -20,
                "total": -120,
                "period": "202006",
                "due": 0,
                "paid": -120
            }
        )
        payment_2 = PurchaseHeader.objects.create(
            **{
                "type": "pp",
                "supplier": self.supplier,
                "ref": self.ref,
                "date": self.date,
                "due_date": self.due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": "202007",
                "due": 0,
                "paid": 0
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": invoice,
                "value": 120,
                "period": "202007"
            }
        )
        PurchaseMatching.objects.create(
            **{
                "matched_by": payment_2,
                "matched_to": payment_1,
                "value": -120,
                "period": "202007"
            }
        )
        outstanding_trans = creditors("202006")
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
                "date": self.date,
                "due_date": self.due_date,
                "goods": 0,
                "vat": 0,
                "total": 0,
                "period": "202006",
                "due": 0,
                "paid": 0
            }
        )
        outstanding_trans = creditors("202006")
        self.assertEqual(
            len(outstanding_trans),
            0
        )
from nominals.models import NominalTransaction
from accountancy.models import TransactionLine
from purchases.models import PurchaseLine
from datetime import date, timedelta

import mock
from accountancy.models import NonAuditQuerySet, Transaction, TransactionHeader
from cashbook.models import CashBook, CashBookHeader
from django.test import TestCase
from nominals.models import Nominal, NominalHeader
from purchases.models import PurchaseHeader, Supplier
from sales.models import SaleHeader


class NonAuditQuerySetTest(TestCase):

    def test_bulk_line_update(self):
        pass
        # # https://www.integralist.co.uk/posts/mocking-in-python/#mock-instance-method
        # with mock.patch('accountancy.models.NonAuditQuerySet.bulk_update') as mock_method:
        #     o = mock.Mock()
        #     o = NonAuditQuerySet.as_manager()
        #     o.model = mock.Mock()
        #     o.model.fields_to_update = mock.Mock()
        #     o.model.fields_to_update.return_value = []
        #     o.bulk_line_update([])
        #     mock_method.assert_called_once()
        #     call = next(iter(mock_method.call_args_list))
        #     args, kwargs = call
        #     objs, fields_to_update = args
        #     assert len(kwargs) == 1
        #     assert objs == []
        #     assert fields_to_update == []
        #     batch_size = kwargs["batch_size"]
        #     assert batch_size is None


class AuditQuerySetTest(TestCase):
    pass


class TransactionTest(TestCase):

    def test_without_header(self):
        class TransactionNew(Transaction):
            module = "PL"

        self.assertRaises(ValueError, TransactionNew)

    def test_without_module(self):
        try:
            class TransactionNew(Transaction):
                pass
            self.fail("Should not allow without module")
        except ValueError:
            pass

    def test_vat_type_on_header(self):
        class Invoice(Transaction):
            module = "PL"
        header = mock.Mock()
        header.vat_type = "i"
        i = Invoice(header=header)
        self.assertEqual(
            i.vat_type,
            "i"
        )

    def test_vat_type_on_transaction_class(self):
        class Invoice(Transaction):
            module = "PL"
            vat_type = "i"
        header = mock.Mock()
        i = Invoice(header=header)
        self.assertEqual(
            i.vat_type,
            "i"
        )


class TransactionHeaderTests(TestCase):
    """
    Since Django out of the box does not yet support creating
    models just for tests I will test this abstract model with a
    real model

    See ticket - https://code.djangoproject.com/ticket/7835 - for
    more info about Django supporting models for testing only.
    """

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code="1", name="1")

    def test_statuses(self):
        statuses = TransactionHeader.statuses
        self.assertEqual(
            statuses,
            [
                ("c", "cleared"),
                ("v", "void"),
            ]
        )

    """
    UI decimal field tests for positive trans
    """

    def test_ui_decimal_field_is_none_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_zero_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_positive_zero_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_integer_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.00"
        )

    def test_ui_decimal_field_is_positive_integer_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.00"
        )

    def test_ui_decimal_field_is_negative_1_decimal_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.10"
        )

    def test_ui_decimal_field_is_positive_1_decimal_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.10"
        )

    def test_ui_decimal_field_is_negative_2_decimal_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.11"
        )

    def test_ui_decimal_field_is_positive_2_decimal_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.11"
        )

    """
    Same tests again but this time check the ui_goods
    """

    def test_ui_decimal_field_is_none_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_zero_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_positive_zero_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_integer_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.00"
        )

    def test_ui_decimal_field_is_positive_integer_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.00"
        )

    def test_ui_decimal_field_is_negative_1_decimal_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.10"
        )

    def test_ui_decimal_field_is_positive_1_decimal_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.10"
        )

    def test_ui_decimal_field_is_negative_2_decimal_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.11"
        )

    def test_ui_decimal_field_is_positive_2_decimal_POSITIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pi",  # POSITIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.11"
        )

    """
    NEGATIVE TRAN
    """

    def test_ui_decimal_field_is_none_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_zero_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_NEGATIVE_zero_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_integer_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.00"
        )

    def test_ui_decimal_field_is_NEGATIVE_integer_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.00"
        )

    def test_ui_decimal_field_is_negative_1_decimal_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.10"
        )

    def test_ui_decimal_field_is_NEGATIVE_1_decimal_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.10"
        )

    def test_ui_decimal_field_is_negative_2_decimal_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=-1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "-1.11"
        )

    def test_ui_decimal_field_is_NEGATIVE_2_decimal_NEGATIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN
            supplier=self.supplier,
            ref="1",
            goods=1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.goods),
            "1.11"
        )

    def test_ui_decimal_field_is_none_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_zero_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_NEGATIVE_zero_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=0.00,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "0.00"
        )

    def test_ui_decimal_field_is_negative_integer_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.00"
        )

    def test_ui_decimal_field_is_NEGATIVE_integer_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.00"
        )

    def test_ui_decimal_field_is_negative_1_decimal_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.10"
        )

    def test_ui_decimal_field_is_NEGATIVE_1_decimal_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1.1,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.10"
        )

    def test_ui_decimal_field_is_negative_2_decimal_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=-1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "1.11"
        )

    def test_ui_decimal_field_is_NEGATIVE_2_decimal_NEGATIVE_TRAN_ui_field_value(self):
        p = PurchaseHeader.objects.create(
            type="pc",  # NEGATIVE TRAN_ui_field_value
            supplier=self.supplier,
            ref="1",
            goods=1.11,
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            str(p.ui_goods),
            "-1.11"
        )

    """
    END OF UI DECIMAL FIELD TESTS
    """

    def test_get_nominal_transaction_factor_positive_and_debit_type(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            pi.get_nominal_transaction_factor(),
            1
        )

    def test_get_nominal_transaction_factor_negative_and_credit_type(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            pc.get_nominal_transaction_factor(),
            1
        )

    def test_get_nominal_transaction_factor_positive_and_credit_type(self):
        si = SaleHeader.objects.create(
            type="si",
            customer=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            si.get_nominal_transaction_factor(),
            -1
        )

    def test_get_nominal_transaction_factor_negative_and_debit_type(self):
        sc = SaleHeader.objects.create(
            type="sc",
            customer=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            sc.get_nominal_transaction_factor(),
            -1
        )

    def test_ui_status_for_nominal_journal(self):
        nj = NominalHeader.objects.create(
            type="nj",
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        self.assertEqual(
            nj.ui_status(),
            ""
        )

    def test_ui_status_for_cash_book_transaction(self):
        nominal = Nominal.objects.create(name="nominal")
        cashbook = CashBook.objects.create(
            name="current",
            nominal=nominal
        )
        cr = CashBookHeader.objects.create(
            type="cr",
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
            cash_book=cashbook
        )
        self.assertEqual(
            cr.ui_status(),
            ""
        )

    def test_ui_status_for_fully_paid(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
            total=100,
            paid=100
        )
        self.assertEqual(
            pi.ui_status(),
            "fully matched"
        )

    def test_ui_status_for_overdue(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today() - timedelta(days=1),
            period="202007",
            total=100,
            paid=90
        )
        self.assertEqual(
            pi.ui_status(),
            "overdue"
        )

    def test_ui_status_for_outstanding(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today() + timedelta(days=1),
            period="202007",
            total=100,
            paid=90
        )
        self.assertEqual(
            pi.ui_status(),
            "outstanding"
        )

    def test_ui_status_no_due_date(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90
        )
        self.assertEqual(
            pi.ui_status(),
            "not fully matched"
        )

    def test_ui_status_void(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertEqual(
            pi.ui_status(),
            "void"
        )

    def test_is_void(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pi.is_void()
        )

    def test_is_positive_type(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pi.is_positive_type()
        )

    def test_is_not_positive_type(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pc.is_positive_type()
        )

    def test_is_payment_type(self):
        pp = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pp.is_payment_type()
        )

    def test_is_not_positive_type(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pc.is_payment_type()
        )

    def test_is_credit_type(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pc.is_credit_type()
        )

    def test_is_not_credit_type(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pi.is_credit_type()
        )

    def test_is_debit_type(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pi.is_debit_type()
        )

    def test_is_not_debit_type(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pc.is_debit_type()
        )

    def test_requires_analysis(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pi.requires_analysis()
        )

    def test_does_not_require_analysis(self):
        pbc = PurchaseHeader.objects.create(
            type="pbc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pbc.requires_analysis()
        )

    def test_requires_lines(self):
        pi = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertTrue(
            pi.requires_lines()
        )

    def test_does_not_require_lines(self):
        pp = PurchaseHeader.objects.create(
            type="pp",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
            status="v"
        )
        self.assertFalse(
            pp.requires_lines()
        )

    def test_get_types_requiring_analysis(self):
        types = PurchaseHeader.get_types_requiring_analysis()
        self.assertEqual(
            types,
            ["pp", "pr", "pi", "pc"]
        )

    def test_get_type_names_requiring_analysis(self):
        types = PurchaseHeader.get_type_names_requiring_analysis()
        self.assertEqual(
            types,
            ["Payment", "Refund", "Invoice", "Credit Note"]
        )

    def test_get_types_requiring_lines(self):
        types = PurchaseHeader.get_types_requiring_lines()
        self.assertEqual(
            types,
            ["pbi", "pbc", "pi", "pc"]
        )

    def test_get_type_names_requiring_lines(self):
        types = PurchaseHeader.get_type_names_requiring_lines()
        self.assertEqual(
            types,
            ["Brought Forward Invoice", "Brought Forward Credit Note",
                "Invoice", "Credit Note"]
        )

    def test_get_debit_types(self):
        self.assertEqual(
            PurchaseHeader.debits,
            [
                'pbi',
                'pbr',
                'pr',
                'pi'
            ]
        )

    def test_get_credit_types(self):
        self.assertEqual(
            PurchaseHeader.credits,
            [
                'pbc',
                'pbp',
                'pp',
                'pc'
            ]
        )

    """
    Test __init_subclass__
    """

    def test_types_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                pass
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify transaction types"
        )

    def test_credits_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which are credits.  If there are none define as an empty list."
            "  A credit transaction is one where a positive value would mean a negative entry in the nominal"
        )

    def test_debits_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which are debits.  If there are none define as an empty list."
            "  A debit transaction is one where a positive value would mean a positive entry in the nominal"
        )

    def test_positives_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
                debits = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which should show as positives on account.  If there are none define as an empty list."
            "  E.g. an invoice is a positive transaction."
        )

    def test_negatives_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
                debits = []
                positives = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which should show as negatives on account.  If there are none define as an empty list."
            "  E.g. a payment is a negative transaction."
        )

    def test_analysis_required_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
                debits = []
                positives = []
                negatives = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which require nominal analysis by the user.  If there are none define as an empty list."
            "  E.g. an invoice requires nominal analysis.  A brought invoice invoice does not."
        )

    def test_lines_required_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
                debits = []
                positives = []
                negatives = []
                analysis_required = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which require lines be shown in the UI.  If there are none define as an empty list."
            "  E.g. an invoice requires lines.  A payment does not."
        )

    def test_payment_types_must_be_defined(self):
        with self.assertRaises(ValueError) as ctx:
            class HeaderTest(TransactionHeader):
                types = []
                credits = []
                debits = []
                positives = []
                negatives = []
                analysis_required = []
                lines_required = []
        self.assertEqual(
            str(ctx.exception),
            "Transaction headers must specify the types which are payment types i.e. will update the cashbook.  If there are none define as an empty list."
        )

    
class TransactionLineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code="1", name="1")

    def test_add_nominal_transactions(self):
        nominal = Nominal(name="nominal")
        header = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=100,
            paid=90,
        )
        line = PurchaseLine(
            header=header,
            line_no=1,
            description="1",
            type="pi"
        )
        g = NominalTransaction(
            module="PL",
            header=1,
            line=1,
            nominal=nominal,
            field="g",
            value=100
        )
        v = NominalTransaction(
            module="PL",
            header=1,
            line=1,
            nominal=nominal,
            field="v",
            value=20
        )
        t = NominalTransaction(
            module="PL",
            header=1,
            line=1,
            nominal=nominal,
            field="t",
            value=-120
        )
        nominal_trans = {
            "g": g,
            "v": v,
            "t": t
        }
        line.add_nominal_transactions(nominal_trans)
        self.assertEqual(
            line.goods_nominal_transaction,
            g
        )
        self.assertEqual(
            line.vat_nominal_transaction,
            v
        )
        self.assertEqual(
            line.total_nominal_transaction,
            t
        )

    def test_is_no_zero_when_zero(self):
        header = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        line = PurchaseLine(
            header=header,
            line_no=1,
            description="1",
            type="pi",
            goods=0,
            vat=0
        )
        self.assertFalse(
            line.is_non_zero()
        )

    def test_is_no_zero_when_non_zero_1(self):
        header = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        line = PurchaseLine(
            header=header,
            line_no=1,
            description="1",
            type="pi",
            goods=100,
            vat=0
        )
        self.assertTrue(
            line.is_non_zero()
        )

    def test_is_no_zero_when_non_zero_2(self):
        header = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        line = PurchaseLine(
            header=header,
            line_no=1,
            description="1",
            type="pi",
            goods=0,
            vat=20
        )
        self.assertTrue(
            line.is_non_zero()
        )
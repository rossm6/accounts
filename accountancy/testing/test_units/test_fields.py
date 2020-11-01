from datetime import date

import mock
from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndChildrenModelChoiceIterator,
                                RootAndLeavesModelChoiceIterator)
from django.test import TestCase
from nominals.models import Nominal
from purchases.models import PurchaseHeader, PurchaseMatching, Supplier
from vat.models import Vat


class UIDecimalFieldTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code="1", name="1")

    """
    UI decimal field tests for positive trans
    """

    def test_ui_decimal_field_as_none_saved_to_db_as_0_POSITIVE_TRAN(self):
        p = PurchaseHeader.objects.create(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        goods = PurchaseHeader.objects.first().__dict__["goods"]
        self.assertEqual(
            str(goods),
            '0.00'
        )

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

    def test_ui_decimal_field_as_none_saved_to_db_as_0_NEGATIVE_TRAN(self):
        pc = PurchaseHeader.objects.create(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            due_date=date.today(),
            period="202007",
        )
        goods = PurchaseHeader.objects.first().__dict__["goods"]
        self.assertEqual(
            str(goods),
            '0.00'
        )

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


class AccountsDecimalFieldTests(TestCase):
    """
    Use PurchaseMatching because the value uses AccountsDecimalField
    """

    @classmethod
    def setUpTestData(cls):
        cls.supplier = Supplier.objects.create(code="1", name="1")

    def test_set_is_not_none(self):
        matched_by = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        matched_to = PurchaseHeader(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=-120,
            paid=0,
        )
        match = PurchaseMatching(
            matched_by=matched_by,
            matched_to=matched_to,
            value=None,
            period="202007",
            matched_by_type="pi",
            matched_to_type="pc"
        )
        self.assertEqual(
            str(match.value),
            '0.00'
        )

    def test_set_is_negative_0(self):
        matched_by = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        matched_to = PurchaseHeader(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=-120,
            paid=0,
        )
        match = PurchaseMatching(
            matched_by=matched_by,
            matched_to=matched_to,
            value=-0,
            period="202007",
            matched_by_type="pi",
            matched_to_type="pc"
        )
        self.assertEqual(
            str(match.value),
            '0.00'
        )

    def test_set_is_non_zero(self):
        matched_by = PurchaseHeader(
            type="pi",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=120,
            paid=0,
        )
        matched_to = PurchaseHeader(
            type="pc",
            supplier=self.supplier,
            ref="1",
            date=date.today(),
            period="202007",
            total=-120,
            paid=0,
        )
        match = PurchaseMatching(
            matched_by=matched_by,
            matched_to=matched_to,
            value=5.65,
            period="202007",
            matched_by_type="pi",
            matched_to_type="pc"
        )
        self.assertEqual(
            str(match.value),
            '5.65'
        )


class RootAndLeavesModelChoiceIteratorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            name="Current Assets", parent=assets)
        cls.sales_ledger_control = Nominal.objects.create(
            name="Sales Ledger Control", parent=current_assets)
        cls.bank_account = Nominal.objects.create(
            name="Bank Account", parent=current_assets)
        cls.prepayments = Nominal.objects.create(
            name="Prepayments", parent=current_assets)
        non_current_assets = Nominal.objects.create(
            name="Non Current Assets", parent=assets)
        cls.land = Nominal.objects.create(
            name="Land", parent=non_current_assets)
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            name="Current Liabilities", parent=liabilities)
        cls.purchase_ledger_control = Nominal.objects.create(name="Purchase Ledger Control",
                                                             parent=current_liabilities)
        cls.vat_control = Nominal.objects.create(
            name="Vat Control", parent=current_liabilities)
        non_current_liabilities = Nominal.objects.create(
            name="Non Current Liabilities", parent=liabilities)
        cls.loans = Nominal.objects.create(
            name="Loans", parent=non_current_liabilities)
        system_controls = Nominal.objects.create(name="System Controls")
        system_suspenses = Nominal.objects.create(
            name="System Suspenses", parent=system_controls)
        cls.system_suspense_account = default_system_suspense = Nominal.objects.create(
            name="System Suspense Account", parent=system_suspenses)

    def test_iterator_empty_label_is_not_none(self):
        field = mock.Mock()
        field.empty_label = ""
        iterator_obj = RootAndLeavesModelChoiceIterator(field)
        it = iter(iterator_obj)
        self.assertEqual(
            next(it),
            ("", "")
        )

    @mock.patch("accountancy.fields.RootAndLeavesModelChoiceIterator.choice")
    def test_iterator_empty_label_is_None(self, mocked_choice):
        field = mock.Mock()
        field.empty_label = None

        def choice(node):
            return node.pk, node.name

        mocked_choice.side_effect = choice
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndLeavesModelChoiceIterator(field)
        it = iter(iterator_obj)

        self.assertEqual(
            next(it),
            (
                "Assets",
                [
                    (self.sales_ledger_control.pk, "Sales Ledger Control"),
                    (self.bank_account.pk, "Bank Account"),
                    (self.prepayments.pk, "Prepayments"),
                    (self.land.pk, "Land")
                ]
            )
        )

        self.assertEqual(
            next(it),
            (
                "Liabilities",
                [
                    (self.purchase_ledger_control.pk, "Purchase Ledger Control"),
                    (self.vat_control.pk, "Vat Control"),
                    (self.loans.pk, "Loans"),
                ]
            )
        )

        self.assertEqual(
            next(it),
            (
                "System Controls",
                [
                    (self.system_suspense_account.pk, "System Suspense Account"),
                ]
            )
        )

        with self.assertRaises(StopIteration):
            next(it)

    def test_len_when_empty_label_is_None(self):
        field = mock.Mock()
        field.empty_label = None
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndLeavesModelChoiceIterator(field)
        self.assertEqual(
            len(iterator_obj),
            11  # roots plus leaves
        )

    def test_len_when_empty_label_is_not_None(self):
        field = mock.Mock()
        field.empty_label = ""
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndLeavesModelChoiceIterator(field)
        self.assertEqual(
            len(iterator_obj),
            12  # roots plus leaves plus empty_label
        )


class RootAndChildrenModelChoiceIteratorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        assets = Nominal.objects.create(name="Assets")
        cls.current_assets = current_assets = Nominal.objects.create(
            name="Current Assets", parent=assets)
        cls.sales_ledger_control = Nominal.objects.create(
            name="Sales Ledger Control", parent=current_assets)
        cls.bank_account = Nominal.objects.create(
            name="Bank Account", parent=current_assets)
        cls.prepayments = Nominal.objects.create(
            name="Prepayments", parent=current_assets)
        cls.non_current_assets = non_current_assets = Nominal.objects.create(
            name="Non Current Assets", parent=assets)
        cls.land = Nominal.objects.create(
            name="Land", parent=non_current_assets)
        cls.liabilities = liabilities = Nominal.objects.create(
            name="Liabilities")
        cls.current_liabilities = current_liabilities = Nominal.objects.create(
            name="Current Liabilities", parent=liabilities)
        cls.purchase_ledger_control = Nominal.objects.create(name="Purchase Ledger Control",
                                                             parent=current_liabilities)
        cls.vat_control = Nominal.objects.create(
            name="Vat Control", parent=current_liabilities)
        cls.non_current_liabilities = non_current_liabilities = Nominal.objects.create(
            name="Non Current Liabilities", parent=liabilities)
        cls.loans = Nominal.objects.create(
            name="Loans", parent=non_current_liabilities)
        cls.system_controls = system_controls = Nominal.objects.create(
            name="System Controls")
        cls.system_suspenses = system_suspenses = Nominal.objects.create(
            name="System Suspenses", parent=system_controls)
        cls.system_suspense_account = default_system_suspense = Nominal.objects.create(
            name="System Suspense Account", parent=system_suspenses)

    def test_empty_label_is_None(self):
        field = mock.Mock()
        field.empty_label = ""
        iterator_obj = RootAndChildrenModelChoiceIterator(field)
        it = iter(iterator_obj)
        self.assertEqual(
            next(it),
            ("", "")
        )

    @mock.patch("accountancy.fields.RootAndChildrenModelChoiceIterator.choice")
    def test_iterations(self, mocked_choice):
        field = mock.Mock()
        field.empty_label = None

        def choice(node):
            return node.pk, node.name

        mocked_choice.side_effect = choice
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndChildrenModelChoiceIterator(field)
        it = iter(iterator_obj)

        self.assertEqual(
            next(it),
            (
                'Assets',
                [
                    (self.current_assets.pk, "Current Assets"),
                    (self.non_current_assets.pk, "Non Current Assets"),
                ]
            )
        )

        self.assertEqual(
            next(it),
            (
                "Liabilities",
                [
                    (self.current_liabilities.pk, "Current Liabilities"),
                    (self.non_current_liabilities.pk, "Non Current Liabilities")
                ]
            )
        )

        self.assertEqual(
            next(it),
            (
                "System Controls",
                [
                    (self.system_suspenses.pk, "System Suspenses"),
                ]
            )
        )

        with self.assertRaises(StopIteration):
            next(it)

    def test_len_when_empty_label_is_None(self):
        field = mock.Mock()
        field.empty_label = None
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndChildrenModelChoiceIterator(field)
        self.assertEqual(
            len(iterator_obj),
            8  # roots plus direct children
        )

    def test_len_when_empty_label_is_not_None(self):
        field = mock.Mock()
        field.empty_label = ""
        field.queryset = Nominal.objects.all().prefetch_related("children")
        iterator_obj = RootAndChildrenModelChoiceIterator(field)
        self.assertEqual(
            len(iterator_obj),
            9  # roots plus leaves plus empty_label
        )


class ModelChoiceIteratorWithFieldsTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.vat_code = Vat.objects.create(
            code="1",
            name="a",
            rate=20
        )

    @mock.patch("accountancy.fields.ModelChoiceIterator.choice")
    def test_choice(self, mocked_choice):
        def choice(o):
            return o.pk, o.code
        mocked_choice.side_effect = choice  # super call is therefore mocked
        it = ModelChoiceIteratorWithFields(mock.Mock())
        c = it.choice(self.vat_code)
        self.assertEqual(
            c,
            (
                self.vat_code.pk,
                self.vat_code.code,
                [
                    ('id', self.vat_code.pk),
                    ('code', self.vat_code.code),
                    ('name', self.vat_code.name),
                    ('rate', self.vat_code.rate),
                    ('registered', self.vat_code.registered)
                ]
            )
        )


class ModelChoiceFieldChooseIteratorTests(TestCase):

    def test_iterator_is_kwarg(self):
        field = ModelChoiceFieldChooseIterator(
            iterator=ModelChoiceIteratorWithFields,
            queryset=Vat.objects.all()
        )
        self.assertEqual(
            field.iterator,
            ModelChoiceIteratorWithFields
        )

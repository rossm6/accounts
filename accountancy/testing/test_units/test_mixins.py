from accountancy.mixins import ControlAccountInvoiceTransactionMixin
from datetime import date

import mock
from accountancy.mixins import VatTransactionMixin
from django.test import TestCase
from vat.models import Vat, VatTransaction

PERIOD = "202007"


class VatTransactionMixinTests(TestCase):

    def test_create_vat_transaction_for_line(self):

        MODULE = "PL"
        TODAY = date.today()

        mock_self = mock.Mock()
        mock_self.module = MODULE
        mock_self.header_obj = mock.Mock()
        mock_self.vat_type = "i"

        mock_self.header_obj.pk = 1
        mock_self.header_obj.ref = "ref"
        mock_self.header_obj.period = PERIOD
        mock_self.header_obj.date = TODAY
        mock_self.header_obj.type = "pi"

        vat_code = Vat(code="1", name="1", rate=20)

        line = mock.Mock()
        line.pk = 1
        line.goods = 100
        line.vat = 20
        line.vat_code = vat_code

        vat_tran_cls = VatTransaction

        vat_tran = VatTransactionMixin._create_vat_transaction_for_line(
            mock_self, line, vat_tran_cls)

        self.assertEqual(
            vat_tran.module,
            MODULE
        )
        self.assertEqual(
            vat_tran.header,
            1
        )
        self.assertEqual(
            vat_tran.line,
            1
        )
        self.assertEqual(
            vat_tran.goods,
            100
        )
        self.assertEqual(
            vat_tran.vat,
            20
        )
        self.assertEqual(
            vat_tran.ref,
            "ref"
        )
        self.assertEqual(
            vat_tran.period,
            PERIOD
        )
        self.assertEqual(
            vat_tran.date,
            TODAY
        )
        self.assertEqual(
            vat_tran.tran_type,
            "pi"
        )
        self.assertEqual(
            vat_tran.vat_type,
            "i"
        )
        self.assertEqual(
            vat_tran.vat_code,
            vat_code
        )
        self.assertEqual(
            vat_tran.vat_rate,
            vat_code.rate
        )
        self.assertEqual(
            vat_tran.field,
            "v"
        )

    def test_create_vat_transactions_for_line_without_vat_code(self):

        line = mock.Mock()
        line.pk = 1

        lines = [line]

        with mock.patch("accountancy.mixins.VatTransactionMixin._create_vat_transaction_for_line") as mocked_create_vat_tran_for_line:
            mocked_create_vat_tran_for_line.return_value = None
            v = VatTransactionMixin()
            v.create_vat_transactions(VatTransaction, lines=lines)

        self.assertEqual(
            len(VatTransaction.objects.all()),
            0
        )

    def test_edit_vat_transaction_for_line_without_vat_code(self):

        TODAY = date.today()

        mock_self = mock.Mock()
        mock_self.header_obj = mock.Mock()
        mock_self.vat_type = "i"

        mock_self.header_obj.ref = "ref"
        mock_self.header_obj.period = PERIOD
        mock_self.header_obj.date = TODAY

        vat_code = Vat(code="1", name="1", rate=20)

        line = mock.Mock()
        line.goods = 100
        line.vat = 20
        line.vat_code = None

        vat_tran_cls = VatTransaction

        vat_tran = mock.Mock()

        return_value = VatTransactionMixin._edit_vat_transaction_for_line(
            mock_self, vat_tran, line)

        self.assertEqual(
            vat_tran,
            return_value
        )
        # i.e. delete this vat_tran

    def test_edit_vat_transaction_for_line_with_vat_code(self):

        TODAY = date.today()

        mock_self = mock.Mock()
        mock_self.header_obj = mock.Mock()
        mock_self.vat_type = "i"

        mock_self.header_obj.ref = "ref"
        mock_self.header_obj.period = PERIOD
        mock_self.header_obj.date = TODAY

        vat_code = Vat(code="1", name="1", rate=20)

        line = mock.Mock()
        line.goods = 100
        line.vat = 20
        line.vat_code = vat_code

        vat_tran_cls = VatTransaction

        vat_tran = mock.Mock()

        return_value = VatTransactionMixin._edit_vat_transaction_for_line(
            mock_self, vat_tran, line)

        self.assertIsNone(return_value)
        # i.e. nothing returned means nothing to delete


from nominals.models import Nominal


class ControlAccountInvoiceTransactionMixinTests(TestCase):

    def test_get_vat_nominal_with_name(self):
        nominal = Nominal(name="Vat Control")
        with mock.patch("nominals.models.Nominal.objects.get") as mocked_get:
            mocked_get.return_value = nominal
            vat_nominal = ControlAccountInvoiceTransactionMixin.get_vat_nominal(
                Nominal,
                vat_nominal_name="Vat Control"
            )
            self.assertEqual(
                vat_nominal,
                nominal
            )

    def test_get_vat_nominal_without_name(self):
        nominal = Nominal(name="Vat Control")
        vat_nominal = ControlAccountInvoiceTransactionMixin.get_vat_nominal(
            Nominal,
            vat_nominal=nominal
        )
        self.assertEqual(
            vat_nominal,
            nominal
        )

    def test_get_control_nominal_with_name(self):
        nominal = Nominal(name="Control")
        with mock.patch("nominals.models.Nominal.objects.get") as mocked_get:
            mocked_get.return_value = nominal
            control_nominal = ControlAccountInvoiceTransactionMixin.get_control_nominal(
                Nominal,
                control_nominal_name="Control"
            )
            self.assertEqual(
                control_nominal,
                nominal
            )

    def test_get_control_nominal_without_name(self):
        nominal = Nominal(name="Control")
        with mock.patch("nominals.models.Nominal.objects.get") as mocked_get:
            mocked_get.return_value = nominal
            control_nominal = ControlAccountInvoiceTransactionMixin.get_control_nominal(
                Nominal,
                control_nominal=nominal
            )
            self.assertEqual(
                control_nominal,
                nominal
            )

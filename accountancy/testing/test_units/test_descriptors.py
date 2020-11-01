from decimal import Decimal

import mock
from accountancy.descriptors import DecimalDescriptor, UIDecimalDescriptor
from django.test import TestCase

TWO_PLACES = Decimal(10) ** -2


class DecimalDescriptorTests(TestCase):
    name = "test_attr"

    def set(self, instance, value):
        # self.name refers to name attribute of Test cls of course
        instance.__dict__[self.name] = value

    def get(self, this, instance=None, owner=None):
        return instance.__dict__[this.name]

    """
    test __get__, mock __set__
    """

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_zero(self, __mocked_set__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.test_attr = Decimal(0.00).quantize(TWO_PLACES)
        self.assertEqual(
            t.test_attr,
            Decimal(0.00).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__set__")
    def test_get_when_attr_is_negative_decimal(self, __mocked_set__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.test_attr = Decimal(-1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            t.test_attr,
            Decimal(-1010.10).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_decimal(self, __mocked_set__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.test_attr = Decimal(1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            t.test_attr,
            Decimal(1010.10).quantize(TWO_PLACES)
        )

    """
    test __set__, mock __get__
    """

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_none(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = None
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            t.test_attr,
            Decimal(0.00).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_negative_zero(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = -0
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_positive_zero(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = 0
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            t.test_attr,
            Decimal(0.00).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_negative_decimal(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = Decimal(-1010.1010)
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            t.test_attr,
            Decimal(-1010.10).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_positive_decimal(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = Decimal(1010.1010)
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            t.test_attr,
            Decimal(1010.10).quantize(TWO_PLACES)
        )


class UIDecimalDescriptorTests(TestCase):
    name = "test_attr"

    def set(self, instance, value):
        instance.__dict__[self.name] = value

    def get(self, this, instance=None, owner=None):
        return instance.__dict__[this.name]

    """
    test __get__, mock __set__.  For negative types
    """

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_zero_NEGATIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_negative_decimal_NEGATIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(-1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "1010.10"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_decimal_NEGATIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "-1010.10"
        )

    """
    test __get__, mock __set__.  For positive types
    """

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_zero_POSITIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_negative_decimal_POSITIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(-1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "-1010.10"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__set__")
    def test_get_when_attr_is_positive_decimal_POSITIVE_TYPE(self, __mocked_set__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "1010.10"
        )


    """
    Test __set__, mock __get__
    """

    """
    NEGATIVE TYPES
    """

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_none_NEGATIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = None
        self.assertEqual(
            str(t.test_attr),
            '0.00'
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_positive_zero_NEGATIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_negative_zero_NEGATIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(-0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_negative_decimal_NEGATIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(-1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "1010.10"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_positive_decimal_NEGATIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = Decimal(1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "-1010.10"
        )

    """
    POSTIVE TYPES
    """

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_none_POSITIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = True
        t.test_attr = None
        self.assertEqual(
            str(t.test_attr),
            '0.00'
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_positive_zero_POSITIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_negative_zero_POSITIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(-0.00).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "0.00"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_negative_decimal_POSITIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(-1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "-1010.10"
        )

    @mock.patch("accountancy.descriptors.UIDecimalDescriptor.__get__")
    def test_set_when_attr_is_positive_decimal_POSITIVE_TYPE(self, __mocked_get__):
        class Test:
            test_attr = UIDecimalDescriptor("test_attr")
        t = Test()
        __mocked_get__.side_effect = self.get
        t.is_negative_type = mock.Mock()
        t.is_negative_type.return_value = False
        t.test_attr = Decimal(1010.101010).quantize(TWO_PLACES)
        self.assertEqual(
            str(t.test_attr),
            "1010.10"
        )
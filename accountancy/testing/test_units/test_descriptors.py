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

    def test_get_when_nothing_set(self):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        self.assertEqual(
            t.test_attr,
            Decimal(0.00).quantize(TWO_PLACES)
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__set__")
    def test_get_when_attr_is_none(self, __mocked_set__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.test_attr = None
        self.assertEqual(
            t.test_attr,
            Decimal(0.00).quantize(TWO_PLACES)
        )

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
    def test_get_when_attr_is_negative_zero(self, __mocked_set__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        __mocked_set__.side_effect = self.set
        t.test_attr = Decimal(-0.00).quantize(TWO_PLACES)
        self.assertEqual(
            t.test_attr,
            Decimal(-0.00).quantize(TWO_PLACES)
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
            None
        )

    @mock.patch("accountancy.descriptors.DecimalDescriptor.__get__")
    def test_set_negative_zero(self, __mocked_get__):
        class Test:
            test_attr = DecimalDescriptor("test_attr")
        t = Test()
        t.test_attr = -0
        __mocked_get__.side_effect = self.get
        self.assertEqual(
            t.test_attr,
            Decimal(-0.00).quantize(TWO_PLACES)
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
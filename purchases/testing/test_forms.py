from datetime import date
from json import loads

from controls.models import FinancialYear, Period
from django.test import TestCase
from purchases.forms import CreditorsForm
from purchases.models import Supplier


class CreditorsFormTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.first_supplier = Supplier.objects.create(name="first")
        cls.second_supplier = Supplier.objects.create(name="second")
        cls.third_supplier = Supplier.objects.create(name="third")
        cls.fy = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_valid_range(self):
        form = CreditorsForm({
            "from_supplier": self.first_supplier.pk,
            "to_supplier": self.second_supplier.pk,
            "period": self.period,
            "use_adv_search": True
        })

        self.assertTrue(
            form.is_valid()
        )

    def test_invalid_range(self):
        form = CreditorsForm({
            "from_supplier": self.third_supplier.pk,
            "to_supplier": self.first_supplier.pk,
            "period": self.period,
            "use_adv_search": True
        })

        self.assertFalse(
            form.is_valid()
        )

        e = form.non_field_errors().as_json()
        e = loads(e)[0]
        self.assertEqual(
            e["message"],
            "This is not a valid range for suppliers because the second supplier you choose comes before the first supplier"
        )
        self.assertEqual(
            e["code"],
            "invalid supplier range"
        )

    def test_single_supplier(self):
        form = CreditorsForm({
            "from_supplier": self.first_supplier.pk,
            "to_supplier": self.first_supplier.pk,
            "period": self.period,
            "use_adv_search": True
        })

        self.assertTrue(
            form.is_valid()
        )

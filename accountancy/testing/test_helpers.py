from django.test import TestCase

from accountancy.helpers import Period


class PeriodTestGeneral(TestCase):

    def test_equality_with_same_objects(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertTrue(
            p1 == p2
        )

    def test_equality_when_not_both_objects_1(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p1 == p2
        )

    def test_equality_when_not_both_objects_2(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p2 == p1
        )

    def test_inequality(self):
        p1 = Period("202007")
        p2 = Period("202006")
        self.assertFalse(
            p1 == p2
        )

    def test_less_than_or_equal_to_with_same_objects_1(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_same_objects_2(self):
        p1 = Period("202006")
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_same_objects_3(self):
        p1 = Period("202008")
        p2 = Period("202007")
        self.assertFalse(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_1(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_2(self):
        p1 = Period("202007")
        p2 = "202008"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_3(self):
        p1 = Period("202008")
        p2 = "202007"
        self.assertFalse(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_4(self):
        p1 = "202007"
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_5(self):
        p1 = "202007"
        p2 = "202008"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_6(self):
        p1 = "202008"
        p2 = Period("202007")
        self.assertFalse(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_1(self):
        p1 = Period("202007")
        p2 = "202008"
        self.assertTrue(
            p1 <= p2
        )

    def test_str(self):
        p = Period("202007")
        self.assertEqual(
            str(p),
            "202007"
        )

class PeriodTestForFYStart(TestCase):
    """
    Here the period added to is always 202001
    """

    def test_sub_0(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 0,
            "202001"
        )

    def test_sub_1(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 1,
            "201912"
        )

    def test_sub_2(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 2,
            "201911"
        )

    def test_sub_3(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 3,
            "201910"
        )

    def test_sub_4(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 4,
            "201909"
        )

    def test_sub_5(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 5,
            "201908"
        )

    def test_sub_6(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 6,
            "201907"
        )

    def test_sub_7(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 7,
            "201906"
        )

    def test_sub_8(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 8,
            "201905"
        )

    def test_sub_9(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 9,
            "201904"
        )

    def test_sub_10(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 10,
            "201903"
        )

    def test_sub_11(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 11,
            "201902"
        )

    def test_sub_12(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 12,
            "201901"
        )

    def test_sub_13(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 13,
            "201812"
        )

    def test_sub_48(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 48,
            "201601"
        )

    def test_add_0(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 0,
            "202001"
        )

    def test_add_1(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 1,
            "202002"
        )

    def test_add_2(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 2,
            "202003"
        )

    def test_add_3(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 3,
            "202004"
        )

    def test_add_4(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 4,
            "202005"
        )

    def test_add_5(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 5,
            "202006"
        )

    def test_add_6(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 6,
            "202007"
        )

    def test_add_7(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 7,
            "202008"
        )

    def test_add_8(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 8,
            "202009"
        )

    def test_add_9(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 9,
            "202010"
        )

    def test_add_10(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 10,
            "202011"
        )

    def test_add_11(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 11,
            "202012"
        )

    def test_add_12(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 12,
            "202101"
        )

    def test_add_13(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 13,
            "202102"
        )

    def test_add_48(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 48,
            "202401"
        )


class PeriodTestForFYEnd(TestCase):
    """
    Here the period added to is always 202012
    """

    def test_sub_0(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 0,
            "202012"
        )

    def test_sub_1(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 1,
            "202011"
        )

    def test_sub_2(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 2,
            "202010"
        )

    def test_sub_3(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 3,
            "202009"
        )

    def test_sub_4(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 4,
            "202008"
        )

    def test_sub_5(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 5,
            "202007"
        )

    def test_sub_6(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 6,
            "202006"
        )

    def test_sub_7(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 7,
            "202005"
        )

    def test_sub_8(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 8,
            "202004"
        )

    def test_sub_9(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 9,
            "202003"
        )

    def test_sub_10(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 10,
            "202002"
        )

    def test_sub_11(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 11,
            "202001"
        )

    def test_sub_12(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 12,
            "201912"
        )

    def test_sub_13(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 13,
            "201911"
        )

    def test_sub_48(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 48,
            "201612"
        )

    def test_add_0(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 0,
            "202012"
        )

    def test_add_1(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 1,
            "202101"
        )

    def test_add_2(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 2,
            "202102"
        )

    def test_add_3(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 3,
            "202103"
        )

    def test_add_4(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 4,
            "202104"
        )

    def test_add_5(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 5,
            "202105"
        )

    def test_add_6(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 6,
            "202106"
        )

    def test_add_7(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 7,
            "202107"
        )

    def test_add_8(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 8,
            "202108"
        )

    def test_add_9(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 9,
            "202109"
        )

    def test_add_10(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 10,
            "202110"
        )

    def test_add_11(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 11,
            "202111"
        )

    def test_add_12(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 12,
            "202112"
        )

    def test_add_13(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 13,
            "202201"
        )
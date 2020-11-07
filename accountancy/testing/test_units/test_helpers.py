from accountancy.helpers import (Period, bulk_delete_with_history,
                                 create_historical_records, get_action,
                                 get_historical_change)
from contacts.models import Contact
from django.db import models
from django.test import TestCase


class GetActionTests(TestCase):

    def test_action_create(self):
        action = get_action("+")
        self.assertEqual(
            action,
            "Create"
        )

    def test_action_update(self):
        action = get_action("~")
        self.assertEqual(
            action,
            "Update"
        )

    def test_action_delete(self):
        action = get_action("-")
        self.assertEqual(
            action,
            "Delete"
        )


class GetHistoricalChangeTests(TestCase):

    def test_historical_change_for_created_audit_only(self):
        """
        Check the changes when only one audit log is provided -
        the audit for the creation of the object
        """
        contact = Contact.objects.create(code="1", name="11", email="111")
        historical_records = Contact.history.all()
        self.assertEqual(
            len(historical_records),
            1
        )
        audit = get_historical_change(None, historical_records[0])
        self.assertEqual(
            audit["id"]["old"],
            ""
        )
        self.assertEqual(
            audit["id"]["new"],
            str(contact.id)
        )
        self.assertEqual(
            audit["code"]["old"],
            ""
        )
        self.assertEqual(
            audit["code"]["new"],
            contact.code
        )
        self.assertEqual(
            audit["email"]["old"],
            ""
        )
        self.assertEqual(
            audit["email"]["new"],
            contact.email
        )

    def test_historical_change_for_updated(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "12"
        contact.save()
        historical_records = Contact.history.all()
        self.assertEqual(
            len(historical_records),
            2
        )
        audit = get_historical_change(
            historical_records[1], historical_records[0]
        )
        self.assertEqual(
            audit["name"]["old"],
            "11"
        )
        self.assertEqual(
            audit["name"]["new"],
            "12"
        )
        self.assertEqual(
            len(audit.keys()),
            2  # the name field - which changed - and the meta field
        )

    def test_historical_change_for_updated_but_no_change(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "11"  # No change !!!
        contact.save()  # Create another log
        historical_records = Contact.history.all()
        self.assertEqual(
            len(historical_records),
            2
        )
        audit = get_historical_change(
            historical_records[1], historical_records[0]
        )
        self.assertIsNone(
            audit
        )

    def test_historical_change_for_deleted(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        pk = contact.pk
        contact.delete()  # Create another log
        historical_records = Contact.history.all()
        self.assertEqual(
            len(historical_records),
            2
        )
        audit = get_historical_change(
            historical_records[1], historical_records[0]
        )
        self.assertEqual(
            audit["meta"]["AUDIT_id"],
            historical_records[0].pk
        )
        self.assertEqual(
            audit["meta"]["AUDIT_action"],
            "Delete"
        )
        self.assertEqual(
            audit["meta"]["object_pk"],
            pk
        )
        self.assertEqual(
            audit["code"]["old"],
            contact.code
        )
        self.assertEqual(
            audit["code"]["new"],
            ""
        )
        self.assertEqual(
            audit["name"]["old"],
            contact.name
        )
        self.assertEqual(
            audit["name"]["new"],
            ""
        )
        self.assertEqual(
            audit["email"]["old"],
            contact.email
        )
        self.assertEqual(
            audit["email"]["new"],
            ""
        )


class CreateHistoricalRecordsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        contacts = []
        for i in range(10):
            c = Contact(code=i, name="duh")
            contacts.append(c)
        Contact.objects.bulk_create(contacts)

    def test_creating_create_audits(self):
        contacts = Contact.objects.all().order_by("pk")
        audits = create_historical_records(contacts, Contact, "+")
        first_audit_pk = audits[0].id
        for i, audit in enumerate(audits, 1):
            self.assertEqual(
                audit.id,
                first_audit_pk + (i - 1)
            )
            self.assertEqual(
                audit.code,
                str(i - 1)
            )
            self.assertEqual(
                audit.name,
                "duh"
            )
            self.assertEqual(
                audit.email,
                ""
            )
            self.assertEqual(
                audit.customer,
                False
            )
            self.assertEqual(
                audit.supplier,
                False
            )
            self.assertEqual(
                audit.history_change_reason,
                ""
            )
            self.assertEqual(
                audit.history_type,
                "+"
            )
            self.assertEqual(
                audit.history_user_id,
                None
            )

    def test_creating_update_audits(self):
        contacts = Contact.objects.all().order_by("pk")
        for c in contacts:
            c.name = "duh-duh"
        Contact.objects.bulk_update(contacts, ["name"])
        audits = create_historical_records(contacts, Contact, "~")
        first_audit_pk = audits[0].id
        for i, audit in enumerate(audits, 1):
            self.assertEqual(
                audit.id,
                first_audit_pk + (i - 1)
            )
            self.assertEqual(
                audit.code,
                str(i - 1)
            )
            self.assertEqual(
                audit.name,
                "duh-duh"
            )
            self.assertEqual(
                audit.email,
                ""
            )
            self.assertEqual(
                audit.customer,
                False
            )
            self.assertEqual(
                audit.supplier,
                False
            )
            self.assertEqual(
                audit.history_change_reason,
                ""
            )
            self.assertEqual(
                audit.history_type,
                "~"
            )
            self.assertEqual(
                audit.history_user_id,
                None
            )

    def test_creating_delete_audits(self):
        contacts = Contact.objects.all().order_by("pk")
        audits = create_historical_records(contacts, Contact, "-")
        first_audit_pk = audits[0].id
        for i, audit in enumerate(audits, 1):
            self.assertEqual(
                audit.id,
                first_audit_pk + (i - 1)
            )
            self.assertEqual(
                audit.code,
                str(i - 1)
            )
            self.assertEqual(
                audit.name,
                "duh"
            )
            self.assertEqual(
                audit.email,
                ""
            )
            self.assertEqual(
                audit.customer,
                False
            )
            self.assertEqual(
                audit.supplier,
                False
            )
            self.assertEqual(
                audit.history_change_reason,
                ""
            )
            self.assertEqual(
                audit.history_type,
                "-"
            )
            self.assertEqual(
                audit.history_user_id,
                None
            )


class BulkDeleteWithHistoryTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        contacts = []
        for i in range(10):
            c = Contact(code=i, name="duh")
            contacts.append(c)
        cls.contacts = Contact.objects.bulk_create(contacts)

    def test(self):
        contacts = self.contacts
        bulk_delete_with_history(contacts, Contact)
        audits = Contact.history.all().order_by("pk")
        first_audit_pk = audits[0].id
        self.assertEqual(
            len(audits),
            10
        )
        for i, audit in enumerate(audits, 1):
            self.assertEqual(
                audit.id,
                first_audit_pk + (i - 1)
            )
            self.assertEqual(
                audit.code,
                str(i - 1)
            )
            self.assertEqual(
                audit.name,
                "duh"
            )
            self.assertEqual(
                audit.email,
                ""
            )
            self.assertEqual(
                audit.customer,
                False
            )
            self.assertEqual(
                audit.supplier,
                False
            )
            self.assertEqual(
                audit.history_change_reason,
                ""
            )
            self.assertEqual(
                audit.history_type,
                "-"
            )
            self.assertEqual(
                audit.history_user_id,
                None
            )


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

    """
    Less than Or Equal To
    """

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

    """
    Less Than
    """

    def test_less_than_with_same_objects_1(self):
        p1 = Period("202006")
        p2 = Period("202007")
        self.assertTrue(
            p1 < p2
        )

    def test_less_than_with_same_objects_2(self):
        p1 = Period("202008")
        p2 = Period("202007")
        self.assertFalse(
            p1 < p2
        )

    def test_less_than_to_with_same_objects_3(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertFalse(
            p1 < p2
        )

    def test_less_than_with_different_objects_1(self):
        p1 = Period("202006")
        p2 = "202007"
        self.assertTrue(
            p1 < p2
        )

    def test_less_than_with_different_objects_2(self):
        p1 = Period("202008")
        p2 = "202007"
        self.assertFalse(
            p1 < p2
        )

    def test_less_than_with_different_objects_3(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertFalse(
            p1 < p2
        )

    def test_less_than_with_different_objects_4(self):
        p1 = "202006"
        p2 = Period("202007")
        self.assertTrue(
            p1 < p2
        )

    def test_less_than_with_different_objects_5(self):
        p1 = "202008"
        p2 = Period("202007")
        self.assertFalse(
            p1 < p2
        )

    def test_less_than_with_different_objects_5(self):
        p1 = "202007"
        p2 = Period("202007")
        self.assertFalse(
            p1 < p2
        )

    """
    Greater Than Or Equal To
    """

    def test_greater_than_or_equal_to_with_same_objects_1(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_same_objects_2(self):
        p1 = Period("202007")
        p2 = Period("202006")
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_same_objects_3(self):
        p1 = Period("202007")
        p2 = Period("202008")
        self.assertFalse(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_1(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_2(self):
        p1 = Period("202008")
        p2 = "202007"
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_3(self):
        p1 = Period("202007")
        p2 = "202008"
        self.assertFalse(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_4(self):
        p1 = "202007"
        p2 = Period("202007")
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_5(self):
        p1 = "202008"
        p2 = "202007"
        self.assertTrue(
            p1 >= p2
        )

    def test_greater_than_or_equal_to_with_different_objects_6(self):
        p1 = "202007"
        p2 = Period("202008")
        self.assertFalse(
            p1 >= p2
        )

    """
    Greater Than
    """

    def test_greater_than_with_same_objects_1(self):
        p1 = Period("202007")
        p2 = Period("202006")
        self.assertTrue(
            p1 > p2
        )

    def test_greater_than_with_same_objects_2(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertFalse(
            p1 > p2
        )

    def test_greater_than_with_same_objects_3(self):
        p1 = Period("202006")
        p2 = Period("202007")
        self.assertFalse(
            p1 > p2
        )

    def test_greater_than_with_different_objects_1(self):
        p1 = Period("202007")
        p2 = "202006"
        self.assertTrue(
            p1 > p2
        )

    def test_greater_than_with_different_objects_2(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertFalse(
            p1 > p2
        )

    def test_greater_than_with_different_objects_3(self):
        p1 = Period("202007")
        p2 = "202008"
        self.assertFalse(
            p1 > p2
        )

    def test_greater_than_with_different_objects_4(self):
        p1 = "202007"
        p2 = Period("202006")
        self.assertTrue(
            p1 > p2
        )

    def test_greater_than_with_different_objects_5(self):
        p1 = "202007"
        p2 = Period("202007")
        self.assertFalse(
            p1 > p2
        )

    def test_greater_than_with_different_objects_5(self):
        p1 = "202006"
        p2 = Period("202007")
        self.assertFalse(
            p1 > p2
        )

    """
    Str
    """

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

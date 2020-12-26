from accountancy.helpers import (bulk_delete_with_history,
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
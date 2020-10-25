from contacts.models import Contact
from django.test import TestCase
from simple_history.models import HistoricalRecords
from utils.helpers import (bulk_delete_with_history,
                           get_all_historical_changes, get_deleted_objects,
                           get_historical_change)


class GetAllHistoricalChangesTest(TestCase):

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
        """
        Simple history will create an audit log even if there have been
        no changes, for performance reasons.

        Periodically we'll need to run a utility they provide to
        remove the duplicates.

        But regardless i don't want to show these duplicates
        in the UI.
        """
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
        """
        Check that a deleted log is returned with values of item
        deleted showing in `old` column, not new.
        """
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

    def test_getting_all_historical_changes(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "12"
        contact.save()
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            2
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            2
        )
        creation_change = changes[0]
        update_change = changes[1]
        self.assertEqual(
            creation_change["id"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["id"]["new"],
            str(contact.id)
        )
        self.assertEqual(
            creation_change["code"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["code"]["new"],
            "1"
        )
        self.assertEqual(
            creation_change["name"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["name"]["new"],
            "11"
        )

        self.assertEqual(
            update_change["name"]["old"],
            "11"
        )
        self.assertEqual(
            update_change["name"]["new"],
            "12"
        )

    def test_getting_deleted_objects(self):
        """
        Where there is no audit log for the deletion.
        Not sure this is really needed...
        """
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "12"
        contact.save()
        historical_records = Contact.history.all().order_by("pk")
        deleted = get_deleted_objects(
            [],
            historical_records,
            Contact._meta.pk.name
        )
        self.assertEqual(
            len(deleted.keys()),
            1
        )
        self.assertEqual(
            list(deleted.keys())[0],
            contact.pk
        )
        self.assertEqual(
            deleted[contact.pk].history_type,
            "-"
        )

    def test_getting_deleted_objects_where_there_exists_an_audit_log_for_deletion(self):
        """
        Where there IS a audit log for the deletion
        """
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "12"
        contact.save()
        contact.delete()
        historical_records = Contact.history.all().order_by("pk")
        deleted = get_deleted_objects(
            [],
            historical_records,
            Contact._meta.pk.name
        )
        self.assertEqual(
            len(deleted.keys()),
            0
        )


class SimpleHistoryBulkDelete(TestCase):

    def setUp(self):
        customers = []
        for i in range(100):
            customers.append(
                Contact(
                    code=i,
                    name="contact" + str(i),
                    email="doris@hotmail.com"
                )
            )
        Contact.objects.bulk_create(customers)

    def test(self):
        customers = Contact.objects.all()
        self.assertEqual(
            len(customers),
            100
        )
        history = Contact.history.all()
        self.assertEqual(
            len(history),
            0
        )
        bulk_delete_with_history(customers, Contact)
        self.assertEqual(
            len(Contact.objects.all()),
            0
        )
        history = Contact.history.all()
        self.assertEqual(
            len(history),
            100  # a history record for object deleted
        )

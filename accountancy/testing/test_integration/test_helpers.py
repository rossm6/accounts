from accountancy.helpers import get_all_historical_changes
from contacts.models import Contact
from django.test import TestCase


class GetAllHistoricalChangesTest(TestCase):

    def test_create_only(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            1
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            1
        )
        creation_change = changes[0]
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
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

    def test_create_and_update(self):
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
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

        self.assertEqual(
            update_change["name"]["old"],
            "11"
        )
        self.assertEqual(
            update_change["name"]["new"],
            "12"
        )
        self.assertEqual(
            update_change["meta"]["AUDIT_action"],
            "Update"
        )


    def test_create_and_update_and_delete(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact_dict = contact.__dict__.copy()
        contact.name = "12"
        contact.save()
        contact.delete()
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            3
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            3
        )
        creation_change = changes[0]
        update_change = changes[1]
        deleted_change = changes[2]
        self.assertEqual(
            creation_change["id"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["id"]["new"],
            str(contact_dict["id"])
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
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

        self.assertEqual(
            update_change["name"]["old"],
            "11"
        )
        self.assertEqual(
            update_change["name"]["new"],
            "12"
        )
        self.assertEqual(
            update_change["meta"]["AUDIT_action"],
            "Update"
        )

        self.assertEqual(
            deleted_change["id"]["old"],
            str(contact_dict["id"])
        )
        self.assertEqual(
            deleted_change["id"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["code"]["old"],
            contact_dict["code"]
        )
        self.assertEqual(
            deleted_change["code"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["name"]["old"],
            "12"
        )
        self.assertEqual(
            deleted_change["name"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["email"]["old"],
            contact_dict["email"]
        )
        self.assertEqual(
            deleted_change["email"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["customer"]["old"],
            str(contact_dict["customer"])
        )
        self.assertEqual(
            deleted_change["customer"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["supplier"]["old"],
            str(contact_dict["supplier"])
        )
        self.assertEqual(
            deleted_change["supplier"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["meta"]["AUDIT_action"],
            "Delete"
        )
from django.test import TestCase
from simple_history.models import HistoricalRecords

from sales.models import Customer
from utils.helpers import (bulk_delete_with_history,
                           get_all_historical_changes, get_deleted_objects,
                           get_historical_change)


class GetAllHistoricalChangesTest(TestCase):

    def test_historical_change_for_created_audit_only(self):
        """
        Check the changes when only one audit log is provided -
        the audit for the creation of the object
        """
        customer = Customer.objects.create(code="1", name="11", email="111")
        historical_records = Customer.history.all()
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
            str(customer.id)
        )
        self.assertEqual(
            audit["code"]["old"],
            ""
        )
        self.assertEqual(
            audit["code"]["new"],
            customer.code
        )
        self.assertEqual(
            audit["email"]["old"],
            ""
        )
        self.assertEqual(
            audit["email"]["new"],
            customer.email
        )

    def test_historical_change_for_updated(self):
        customer = Customer.objects.create(code="1", name="11", email="111")
        customer.name = "12"
        customer.save()
        historical_records = Customer.history.all()
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
            2 # the name field - which changed - and the meta field
        )

    def test_getting_all_historical_changes(self):
        customer = Customer.objects.create(code="1", name="11", email="111")
        customer.name = "12"
        customer.save()
        historical_records = Customer.history.all().order_by("pk")
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
            str(customer.id)
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
        Where there is no audit log for the deletion
        """
        customer = Customer.objects.create(code="1", name="11", email="111")
        customer.name = "12"
        customer.save()
        historical_records = Customer.history.all().order_by("pk")
        deleted = get_deleted_objects(
            [], 
            historical_records,
            Customer._meta.pk.name
        )
        self.assertEqual(
            len(deleted.keys()),
            1
        )
        self.assertEqual(
            list(deleted.keys())[0],
            customer.pk
        )
        self.assertEqual(
            deleted[customer.pk].history_type,
            "-"
        )

    def test_getting_deleted_objects_where_there_exists_an_audit_log_for_deletion(self):
        """
        Where there IS a audit log for the deletion
        """
        customer = Customer.objects.create(code="1", name="11", email="111")
        customer.name = "12"
        customer.save()
        customer.delete()
        historical_records = Customer.history.all().order_by("pk")
        deleted = get_deleted_objects(
            [], 
            historical_records,
            Customer._meta.pk.name
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
                Customer(
                    code=i,
                    name="customer" + str(i),
                    email="doris@hotmail.com"
                )
            )
        Customer.objects.bulk_create(customers)

    def test(self):
        customers = Customer.objects.all()
        self.assertEqual(
            len(customers),
            100
        )
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            0
        )
        bulk_delete_with_history(customers, Customer)
        self.assertEqual(
            len(Customer.objects.all()),
            0
        )
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            100  # a history record for object deleted
        )
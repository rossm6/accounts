from django.test import TestCase
from simple_history.models import HistoricalRecords

from sales.models import Customer
from utils.helpers import bulk_delete_with_history


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
            100 # a history record for object deleted
        )


    def test_signal_reconnected(self):
        """
        Check that a reconnection is made.
        """
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
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            100
        )
        self.assertEqual(
            len(Customer.objects.all()),
            0
        )
        self.assertEqual(
            len(history),
            100 # extra has been created automatically by simple history
        ) 
        customer = Customer.objects.create(code="1", name="1", email="duh")
        customer.delete()
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            102 # extra has been created automatically by simple history
            # one for create and another for delete
        )

    def test_signal_reconnected_but_object_doest_not_log_audit_FAILURE(self):
        """
        
        I noticed this when testing.  Not the expected behaviour but
        i don't know what i'm doing wrong.  Is this a bug?

        Shouldn't be a problem anyway but needs to be included in tests
        in case strange things to happen...

        I presume each instance object contains a reference to the post_delete
        signal which has since been deleted.

        """
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
        last_customer = customers[99]
        customers = customers[:99]
        bulk_delete_with_history(customers, Customer)
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            99
        )
        self.assertEqual(
            len(Customer.objects.all()),
            1
        )
        last_customer.delete()
        self.assertEqual(
            len(history),
            100 # extra has been created automatically by simple history
        ) 
        customer = Customer.objects.create(code="1", name="1", email="duh")
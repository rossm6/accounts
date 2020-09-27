from django.test import TestCase

from sales.models import Customer
from utils.helpers import bulk_delete_with_history
from simple_history.models import HistoricalRecords

from django.db import models

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
        models.signals.post_delete.disconnect(HistoricalRecords.post_delete, sender=Customer)
        bulk_delete_with_history(customers, Customer)
        history = Customer.history.all()
        self.assertEqual(
            len(history),
            100 # a history record for object deleted
        )
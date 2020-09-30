from django.test import TestCase

from sales.models import Customer

class DeleteSignalTest(TestCase):

    def setUp(self):
        c = Customer.objects.create(
            code="1",
            name="11",
            email="111"
        )
    
    def test_deleting_instance_object_triggers_signal(self):
        c = Customer.objects.first()
        self.assertEqual(
            len(Customer.history.all()),
            1 # the audit log for the creation
        )
        c.delete()
        self.assertEqual(
            len(Customer.history.all()),
            2
        )  
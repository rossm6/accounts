from contacts.models import Contact
from django.test import TestCase


class DeleteSignalTest(TestCase):

    def setUp(self):
        c = Contact.objects.create(
            code="1",
            name="11",
            email="111"
        )
    
    def test_deleting_instance_object_triggers_signal(self):
        c = Contact.objects.first()
        self.assertEqual(
            len(Contact.history.all()),
            1 # the audit log for the creation
        )
        c.delete()
        self.assertEqual(
            len(Contact.history.all()),
            2
        )  

from accountancy.helpers import bulk_delete_with_history
from accountancy.signals import audit_post_delete
from contacts.models import Contact
from django.test import TestCase
from simple_history.models import HistoricalRecords
from django.db import models


class ContactAuditTests(TestCase):
    """
    Check that the app is set up correctly i.e. right signals are set up,
    and it is registered with simple history package.
    """

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(Contact)
        for receiver in live_receivers:
            if receiver.__self__.__class__.__name__ == HistoricalRecords.__name__:
                self.fail(
                    """
                    Historical Records receiver not disconnected.  
                    It should be because we are using our own custom signal 
                    which is fired when we delete."""
                )

    def test_audit_post_delete_signal_is_added(self):
        """
        After registering the model and disconnecting the receiver from
        the post delete signal we add our receiver to a custom signal
        """
        live_receivers = audit_post_delete._live_receivers(Contact)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'contacts.models.Contact'>>":
                found = True
            break
        if not found:
            self.fail("Failed to find the post_delete method of the AuditMixin class")

    def test_instance_deleted(self):
        c = Contact(
            code="1",
            name="contact1",
            email="doris@hotmail.com"
        )
        c.save()
        c.delete()
        self.assertEqual(
            len(
                Contact.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        c = Contact(
            code="1",
            name="contact1",
            email="doris@hotmail.com"
        )
        c.save()
        Contact.objects.all().delete()
        self.assertEqual(
            len(
                Contact.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )
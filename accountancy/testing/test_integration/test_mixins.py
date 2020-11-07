from accountancy.helpers import bulk_delete_with_history
from accountancy.mixins import SingleObjectAuditDetailViewMixin
from accountancy.signals import audit_post_delete
from contacts.models import Contact
from django.db import models
from django.test import TestCase
from simple_history.models import HistoricalRecords


class AuditMixinTest(TestCase):
    """
    These integration tests use the Contact model as an example.  Each app should also contain the same tests.
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
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

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

    # USE THIS LATER FOR TESTING BULK_DELETE_WITH_HISTORY
    # def test_bulk_deleted(self):
    #     contacts = []
    #     for i in range(100):
    #         contacts.append(
    #             Contact(
    #                 code=i,
    #                 name="contact" + str(i),
    #                 email="doris@hotmail.com"
    #             )
    #         )
    #     Contact.objects.bulk_create(contacts)
    #     contacts = Contact.objects.all()
    #     self.assertEqual(
    #         len(contacts),
    #         100
    #     )
    #     history = Contact.history.all()
    #     self.assertEqual(
    #         len(history),
    #         0 # because audited_bulk_create not used
    #     )
    #     bulk_delete_with_history(contacts, Contact)
    #     self.assertEqual(
    #         len(Contact.objects.all()),
    #         0
    #     )
    #     history = Contact.history.all()
    #     self.assertEqual(
    #         len(history),
    #         100  # a history record for object deleted
    #     )
    #     # this proves that the post_delete signal was not received
    #     # by the simple_history post_delete receiver

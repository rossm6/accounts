from datetime import date

from accountancy.signals import audit_post_delete
from django.db import models
from django.test import TestCase
from simple_history.models import HistoricalRecords
from vat.models import Vat, VatTransaction


class VatAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(Vat)
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
        live_receivers = audit_post_delete._live_receivers(Vat)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'vat.models.Vat'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        n = Vat.objects.create(code="1", name="1", rate=20)
        self.assertEqual(
            len(
                Vat.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        n = Vat.objects.create(code="1", name="1", rate=20)
        n.name = "new Vat"
        n.save()
        self.assertEqual(
            len(
                Vat.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Vat.objects.create(code="1", name="1", rate=20)
        n.delete()
        self.assertEqual(
            len(
                Vat.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Vat.objects.create(code="1", name="1", rate=20)
        Vat.objects.all().delete()
        self.assertEqual(
            len(
                Vat.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class VatTransactionAuditTests(TestCase):

    def test_no_historical_model_exists(self):
        if hasattr(VatTransaction, "history"):
            self.fail("This model should not be audited")

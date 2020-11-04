from datetime import date

from accountancy.signals import audit_post_delete
from django.db import models
from django.test import TestCase
from nominals.models import (Nominal, NominalHeader, NominalLine,
                             NominalTransaction)
from simple_history.models import HistoricalRecords


class NominalAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(Nominal)
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
        live_receivers = audit_post_delete._live_receivers(Nominal)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'nominals.models.Nominal'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        n = Nominal.objects.create(name="nominal")
        self.assertEqual(
            len(
                Nominal.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        n = Nominal.objects.create(name="nominal")
        n.name = "new nominal"
        n.save()
        self.assertEqual(
            len(
                Nominal.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Nominal.objects.create(name="nominal")
        n.delete()
        self.assertEqual(
            len(
                Nominal.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Nominal.objects.create(name="nominal")
        Nominal.objects.all().delete()
        self.assertEqual(
            len(
                Nominal.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class NominalHeaderAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            NominalHeader)
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
        live_receivers = audit_post_delete._live_receivers(NominalHeader)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'nominals.models.NominalHeader'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        n = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        n = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        n.ref = "11"
        n.save()
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        n.delete()
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        NominalHeader.objects.all().delete()
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class NominalLineAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            NominalLine)
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
        live_receivers = audit_post_delete._live_receivers(NominalLine)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'nominals.models.NominalLine'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        n = Nominal.objects.create(name="n")
        h = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        l = NominalLine.objects.create(header=h, line_no="1", description="d", nominal=n)
        self.assertEqual(
            len(
                NominalLine.history.all()
            ),
            1  # created audits
        )

    def test_audit_is_updated(self):
        n = Nominal.objects.create(name="n")
        h = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        l = NominalLine.objects.create(header=h, line_no="1", description="d", nominal=n)
        l.line_no = "2"
        l.save()
        self.assertEqual(
            len(
                NominalLine.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Nominal.objects.create(name="n")
        h = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        l = NominalLine.objects.create(header=h, line_no="1", description="d", nominal=n)
        l.delete()
        self.assertEqual(
            len(
                NominalLine.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Nominal.objects.create(name="n")
        h = NominalHeader.objects.create(
            ref="1",
            date=date.today()
        )
        l = NominalLine.objects.create(header=h, line_no="1", description="d", nominal=n)
        NominalLine.objects.all().delete()
        self.assertEqual(
            len(
                NominalLine.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class NominalTransactionAuditTests(TestCase):

    def test_no_historical_model_exists(self):
        if hasattr(NominalTransaction, "history"):
            self.fail("This model should not be audited")

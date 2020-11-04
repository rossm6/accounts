from datetime import date

from accountancy.signals import audit_post_delete
from django.db import models
from django.test import TestCase
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)
from simple_history.models import HistoricalRecords

PERIOD = "202007"


class SupplierAuditTests(TestCase):

    """
    Supplier is just a proxy model of Contact.  Audits will be kept for changes made via the
    Contact model only.
    """

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(Supplier)
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
        SUPPLIER MODEL SHOULD NOT BE AUDITED.  CONTACT MODEL IS.
        """
        live_receivers = audit_post_delete._live_receivers(Supplier)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'purchases.models.Supplier'>>":
                found = True
            break
        if found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    def test_audit_is_not_created(self):
        s = Supplier.objects.create(code="1", name="11")
        self.assertEqual(
            len(
                Supplier.history.all()
            ),
            0
        )

    def test_audit_is_not_updated(self):
        s = Supplier.objects.create(code="1", name="11")
        s.name = "new supplier"
        s.save()
        self.assertEqual(
            len(
                Supplier.history.all()
            ),
            0
        )

    def test_instance_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        s.delete()
        self.assertEqual(
            len(
                Supplier.history.all()
            ),
            0
        )

    def test_queryset_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        Supplier.objects.all().delete()
        self.assertEqual(
            len(
                Supplier.history.all()
            ),
            0
        )


class PurchaseHeaderAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            PurchaseHeader)
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
        live_receivers = audit_post_delete._live_receivers(PurchaseHeader)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'purchases.models.PurchaseHeader'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        s = Supplier.objects.create(code="1", name="11")
        n = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        self.assertEqual(
            len(
                PurchaseHeader.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        s = Supplier.objects.create(code="1", name="11")
        n = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        n.ref = "11"
        n.save()
        self.assertEqual(
            len(
                PurchaseHeader.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        n = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        n.delete()
        self.assertEqual(
            len(
                PurchaseHeader.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        n = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        PurchaseHeader.objects.all().delete()
        self.assertEqual(
            len(
                PurchaseHeader.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class PurchaseLineAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            PurchaseLine)
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
        live_receivers = audit_post_delete._live_receivers(PurchaseLine)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'purchases.models.PurchaseLine'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        s = Supplier.objects.create(code="1", name="11")
        h = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        l = PurchaseLine.objects.create(
            header=h, line_no="1", description="d")
        self.assertEqual(
            len(
                PurchaseLine.history.all()
            ),
            1  # created audits
        )

    def test_audit_is_updated(self):
        s = Supplier.objects.create(code="1", name="11")
        h = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        l = PurchaseLine.objects.create(
            header=h, line_no="1", description="d")
        l.line_no = "2"
        l.save()
        self.assertEqual(
            len(
                PurchaseLine.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        h = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        l = PurchaseLine.objects.create(
            header=h, line_no="1", description="d")
        l.delete()
        self.assertEqual(
            len(
                PurchaseLine.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        h = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        l = PurchaseLine.objects.create(
            header=h, line_no="1", description="d")
        PurchaseLine.objects.all().delete()
        self.assertEqual(
            len(
                PurchaseLine.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class PurchaseMatchingAuditTests(TestCase):
    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            PurchaseMatching)
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
        live_receivers = audit_post_delete._live_receivers(PurchaseMatching)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'purchases.models.PurchaseMatching'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        s = Supplier.objects.create(code="1", name="11")
        h1 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        h2 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        m = PurchaseMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=PERIOD,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        self.assertEqual(
            len(
                PurchaseMatching.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        s = Supplier.objects.create(code="1", name="11")
        h1 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        h2 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        m = PurchaseMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=PERIOD,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        m.period = "202008"
        m.save()
        self.assertEqual(
            len(
                PurchaseMatching.history.all()
            ),
            2  # created + updated audit
        )

    def test_instance_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        h1 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        h2 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        m = PurchaseMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=PERIOD,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        m.delete()
        self.assertEqual(
            len(
                PurchaseMatching.history.all()
            ),
            2  # created + deleted audit
        )

    def test_queryset_deleted(self):
        s = Supplier.objects.create(code="1", name="11")
        h1 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        h2 = PurchaseHeader.objects.create(
            supplier=s,
            ref="1",
            date=date.today()
        )
        m = PurchaseMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=PERIOD,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        PurchaseMatching.objects.all().delete()
        self.assertEqual(
            len(
                PurchaseMatching.history.all()
            ),
            1  # created audit only
        )

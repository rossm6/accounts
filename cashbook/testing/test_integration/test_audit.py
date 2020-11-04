from datetime import date

from accountancy.signals import audit_post_delete
from cashbook.models import (CashBook, CashBookHeader, CashBookLine,
                             CashBookTransaction)
from django.db import models
from django.test import TestCase
from nominals.models import Nominal
from simple_history.models import HistoricalRecords


class CashBookAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(CashBook)
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
        live_receivers = audit_post_delete._live_receivers(CashBook)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'cashbook.models.CashBook'>>":
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
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        self.assertEqual(
            len(
                CashBook.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        c.name = "new name"
        c.save()
        self.assertEqual(
            len(
                CashBook.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        c.delete()
        self.assertEqual(
            len(
                CashBook.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        CashBook.objects.all().delete()
        self.assertEqual(
            len(
                CashBook.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class CashBookHeaderAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            CashBookHeader)
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
        live_receivers = audit_post_delete._live_receivers(CashBookHeader)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'cashbook.models.CashBookHeader'>>":
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
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        t = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        t.save()
        self.assertEqual(
            len(
                CashBookHeader.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        t = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        t.save()
        t.date = date.today()
        t.save()
        self.assertEqual(
            len(
                CashBookHeader.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        t = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        t.save()
        t.delete()
        self.assertEqual(
            len(
                CashBookHeader.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        t = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        t.save()
        CashBookHeader.objects.all().delete()
        self.assertEqual(
            len(
                CashBookHeader.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class CashBookLineAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            CashBookLine)
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
        live_receivers = audit_post_delete._live_receivers(CashBookLine)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'cashbook.models.CashBookLine'>>":
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
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        h = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        h.save()
        l = CashBookLine.objects.create(
            header=h, line_no=1, description="description")
        self.assertEqual(
            len(
                CashBookLine.history.all()
            ),
            1  # created audits
        )

    def test_audit_is_updated(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        h = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        h.save()
        l = CashBookLine.objects.create(
            header=h, line_no=1, description="description")
        l.description = "new description"
        l.save()
        self.assertEqual(
            len(
                CashBookLine.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        h = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        h.save()
        l = CashBookLine.objects.create(
            header=h, line_no=1, description="description")
        l.delete()
        self.assertEqual(
            len(
                CashBookLine.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        n = Nominal.objects.create(name="nominal")
        c = CashBook(
            name="current",
            nominal=n
        )
        c.save()
        h = CashBookHeader(
            date=date.today(),
            cash_book=c
        )
        h.save()
        l = CashBookLine.objects.create(
            header=h, line_no=1, description="description")
        CashBookLine.objects.all().delete()
        self.assertEqual(
            len(
                CashBookLine.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class CashBookTransactionAuditTests(TestCase):

    def test_no_historical_model_exists(self):
        if hasattr(CashBookTransaction, "history"):
            self.fail("This model should not be audited")

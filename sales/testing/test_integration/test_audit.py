from datetime import date

from accountancy.signals import audit_post_delete
from django.db import models
from django.test import TestCase
from sales.models import Customer, SaleHeader, SaleLine, SaleMatching
from simple_history.models import HistoricalRecords
from controls.models import FinancialYear, Period


class CustomerAuditTests(TestCase):

    """
    Customer is just a proxy model of Contact.  Audits will be kept for changes made via the
    Contact model only.
    """

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(Customer)
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
        customer MODEL SHOULD NOT BE AUDITED.  CONTACT MODEL IS.
        """
        live_receivers = audit_post_delete._live_receivers(Customer)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'sales.models.Customer'>>":
                found = True
            break
        if found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    def test_audit_is_not_created(self):
        s = Customer.objects.create(code="1", name="11")
        self.assertEqual(
            len(
                Customer.history.all()
            ),
            0
        )

    def test_audit_is_not_updated(self):
        s = Customer.objects.create(code="1", name="11")
        s.name = "new customer"
        s.save()
        self.assertEqual(
            len(
                Customer.history.all()
            ),
            0
        )

    def test_instance_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        s.delete()
        self.assertEqual(
            len(
                Customer.history.all()
            ),
            0
        )

    def test_queryset_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        Customer.objects.all().delete()
        self.assertEqual(
            len(
                Customer.history.all()
            ),
            0
        )


class SaleHeaderAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            SaleHeader)
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
        live_receivers = audit_post_delete._live_receivers(SaleHeader)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'sales.models.SaleHeader'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        s = Customer.objects.create(code="1", name="11")
        n = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        self.assertEqual(
            len(
                SaleHeader.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        s = Customer.objects.create(code="1", name="11")
        n = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        n.ref = "11"
        n.save()
        self.assertEqual(
            len(
                SaleHeader.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        n = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        n.delete()
        self.assertEqual(
            len(
                SaleHeader.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        n = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        SaleHeader.objects.all().delete()
        self.assertEqual(
            len(
                SaleHeader.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class SaleLineAuditTests(TestCase):

    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            SaleLine)
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
        live_receivers = audit_post_delete._live_receivers(SaleLine)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'sales.models.SaleLine'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        s = Customer.objects.create(code="1", name="11")
        h = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        l = SaleLine.objects.create(
            header=h, line_no="1", description="d")
        self.assertEqual(
            len(
                SaleLine.history.all()
            ),
            1  # created audits
        )

    def test_audit_is_updated(self):
        s = Customer.objects.create(code="1", name="11")
        h = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        l = SaleLine.objects.create(
            header=h, line_no="1", description="d")
        l.line_no = "2"
        l.save()
        self.assertEqual(
            len(
                SaleLine.history.all()
            ),
            2  # created + updated audits
        )

    def test_instance_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        h = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        l = SaleLine.objects.create(
            header=h, line_no="1", description="d")
        l.delete()
        self.assertEqual(
            len(
                SaleLine.history.all()
            ),
            2  # created + deleted audits
        )

    def test_queryset_deleted(self):
        s = Customer.objects.create(code="1", name="11")
        h = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        l = SaleLine.objects.create(
            header=h, line_no="1", description="d")
        SaleLine.objects.all().delete()
        self.assertEqual(
            len(
                SaleLine.history.all()
            ),
            1  # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )


class SaleMatchingAuditTests(TestCase):
    def test_simple_history_post_delete_receiver_is_removed(self):
        """
        The ready method of the AppConfig calls simple_history_custom_set_up
        on the AuditMixin class which disconnects this receiver.
        """
        live_receivers = models.signals.post_delete._live_receivers(
            SaleMatching)
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
        live_receivers = audit_post_delete._live_receivers(SaleMatching)
        found = False
        for receiver in live_receivers:
            if str(receiver) == "<bound method AuditMixin.post_delete of <class 'sales.models.SaleMatching'>>":
                found = True
            break
        if not found:
            self.fail(
                "Failed to find the post_delete method of the AuditMixin class")

    """
    Create and update are taken care of by the app simple_history.  Just check here that is working.
    """

    def test_audit_is_created(self):
        fy = FinancialYear.objects.create(financial_year=2020)
        period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        s = Customer.objects.create(code="1", name="11")
        h1 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        h2 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        m = SaleMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=period,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        self.assertEqual(
            len(
                SaleMatching.history.all()
            ),
            1  # created audit
        )

    def test_audit_is_updated(self):
        fy = FinancialYear.objects.create(financial_year=2020)
        period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        s = Customer.objects.create(code="1", name="11")
        h1 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        h2 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        m = SaleMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=period,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        m.save()
        self.assertEqual(
            len(
                SaleMatching.history.all()
            ),
            2  # created + updated audit
        )

    def test_instance_deleted(self):
        fy = FinancialYear.objects.create(financial_year=2020)
        period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        s = Customer.objects.create(code="1", name="11")
        h1 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        h2 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        m = SaleMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=period,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        m.delete()
        self.assertEqual(
            len(
                SaleMatching.history.all()
            ),
            2  # created + deleted audit
        )

    def test_queryset_deleted(self):
        fy = FinancialYear.objects.create(financial_year=2020)
        period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))
        s = Customer.objects.create(code="1", name="11")
        h1 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        h2 = SaleHeader.objects.create(
            customer=s,
            ref="1",
            date=date.today()
        )
        m = SaleMatching.objects.create(
            matched_by=h1,
            matched_to=h2,
            period=period,
            matched_by_type=h1.type,
            matched_to_type=h2.type
        )
        SaleMatching.objects.all().delete()
        self.assertEqual(
            len(
                SaleMatching.history.all()
            ),
            1  # created audit only
        )
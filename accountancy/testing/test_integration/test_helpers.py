from datetime import date, datetime, timedelta

from accountancy.helpers import AuditTransaction, get_all_historical_changes
from cashbook.models import CashBook
from contacts.models import Contact
from controls.models import FinancialYear, Period
from django.test import TestCase
from nominals.models import Nominal
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)
from vat.models import Vat

DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'


class GetAllHistoricalChangesTest(TestCase):

    def test_create_only(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            1
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            1
        )
        creation_change = changes[0]
        self.assertEqual(
            creation_change["id"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["id"]["new"],
            str(contact.id)
        )
        self.assertEqual(
            creation_change["code"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["code"]["new"],
            "1"
        )
        self.assertEqual(
            creation_change["name"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["name"]["new"],
            "11"
        )
        self.assertEqual(
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

    def test_create_and_update(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact.name = "12"
        contact.save()
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            2
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            2
        )
        creation_change = changes[0]
        update_change = changes[1]
        self.assertEqual(
            creation_change["id"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["id"]["new"],
            str(contact.id)
        )
        self.assertEqual(
            creation_change["code"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["code"]["new"],
            "1"
        )
        self.assertEqual(
            creation_change["name"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["name"]["new"],
            "11"
        )
        self.assertEqual(
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

        self.assertEqual(
            update_change["name"]["old"],
            "11"
        )
        self.assertEqual(
            update_change["name"]["new"],
            "12"
        )
        self.assertEqual(
            update_change["meta"]["AUDIT_action"],
            "Update"
        )

    def test_create_and_update_and_delete(self):
        contact = Contact.objects.create(code="1", name="11", email="111")
        contact_dict = contact.__dict__.copy()
        contact.name = "12"
        contact.save()
        contact.delete()
        historical_records = Contact.history.all().order_by("pk")
        self.assertEqual(
            len(historical_records),
            3
        )
        changes = get_all_historical_changes(historical_records)
        self.assertEqual(
            len(changes),
            3
        )
        creation_change = changes[0]
        update_change = changes[1]
        deleted_change = changes[2]
        self.assertEqual(
            creation_change["id"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["id"]["new"],
            str(contact_dict["id"])
        )
        self.assertEqual(
            creation_change["code"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["code"]["new"],
            "1"
        )
        self.assertEqual(
            creation_change["name"]["old"],
            ""
        )
        self.assertEqual(
            creation_change["name"]["new"],
            "11"
        )
        self.assertEqual(
            creation_change["meta"]["AUDIT_action"],
            "Create"
        )

        self.assertEqual(
            update_change["name"]["old"],
            "11"
        )
        self.assertEqual(
            update_change["name"]["new"],
            "12"
        )
        self.assertEqual(
            update_change["meta"]["AUDIT_action"],
            "Update"
        )

        self.assertEqual(
            deleted_change["id"]["old"],
            str(contact_dict["id"])
        )
        self.assertEqual(
            deleted_change["id"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["code"]["old"],
            contact_dict["code"]
        )
        self.assertEqual(
            deleted_change["code"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["name"]["old"],
            "12"
        )
        self.assertEqual(
            deleted_change["name"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["email"]["old"],
            contact_dict["email"]
        )
        self.assertEqual(
            deleted_change["email"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["customer"]["old"],
            str(contact_dict["customer"])
        )
        self.assertEqual(
            deleted_change["customer"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["supplier"]["old"],
            str(contact_dict["supplier"])
        )
        self.assertEqual(
            deleted_change["supplier"]["new"],
            ""
        )
        self.assertEqual(
            deleted_change["meta"]["AUDIT_action"],
            "Delete"
        )


class AuditTransactionTest(TestCase):
    """
    Test with PL header, line, matching
    """

    @classmethod
    def setUpTestData(cls):
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                              ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.fy = fy
        cls.period = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))

    def test_no_lines(self):
        cash_book = CashBook.objects.create(
            nominal=None,
            name="current"
        )
        supplier = Supplier.objects.create(
            code="1",
            name="2",
            email="3"
        )
        h = PurchaseHeader.objects.create(
            type="pp",  # payment
            date=date.today(),
            goods=120,
            vat=0,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period=self.period
        )
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            1
        )
        h.ref = "1234"  # update the header
        h.save()
        h.refresh_from_db()
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            2
        )
        audit_transaction = AuditTransaction(
            h, PurchaseHeader, PurchaseLine, PurchaseMatching)
        self.assertEqual(
            len(audit_transaction.audit_header_history),
            2
        )
        self.assertEqual(
            len(audit_transaction.audit_lines_history),
            0
        )
        self.assertEqual(
            len(audit_transaction.audit_matches_history),
            0
        )
        all_changes = audit_transaction.get_historical_changes()
        self.assertEqual(
            len(all_changes),
            2
        )
        self.assertTrue(
            all_changes[0]["meta"]["AUDIT_date"] < all_changes[1]["meta"]["AUDIT_date"]
        )
        create = all_changes[0]
        self.assertEqual(
            create["id"]["old"],
            "",
        )
        self.assertEqual(
            create["id"]["new"],
            str(h.id),
        )
        self.assertEqual(
            create["ref"]["old"],
            "",
        )
        self.assertEqual(
            create["ref"]["new"],
            "123",
        )
        self.assertEqual(
            create["goods"]["old"],
            "",
        )
        self.assertEqual(
            create["goods"]["new"],
            str(h.goods),
        )
        self.assertEqual(
            create["vat"]["old"],
            "",
        )
        self.assertEqual(
            create["vat"]["new"],
            str(h.vat),
        )
        self.assertEqual(
            create["total"]["old"],
            "",
        )
        self.assertEqual(
            create["total"]["new"],
            str(h.total),
        )
        self.assertEqual(
            create["paid"]["old"],
            "",
        )
        self.assertEqual(
            create["paid"]["new"],
            str(h.paid),
        )
        self.assertEqual(
            create["due"]["old"],
            "",
        )
        self.assertEqual(
            create["due"]["new"],
            str(h.due),
        )
        self.assertEqual(
            create["date"]["old"],
            "",
        )
        self.assertEqual(
            create["date"]["new"],
            str(h.date),
        )
        self.assertEqual(
            create["due_date"]["old"],
            "",
        )
        self.assertEqual(
            create["due_date"]["new"],
            str(h.due_date),
        )
        self.assertEqual(
            create["period_id"]["old"],
            "",
        )
        self.assertEqual(
            create["period_id"]["new"],
            str(self.period.pk),
        )
        self.assertEqual(
            create["status"]["old"],
            "",
        )
        self.assertEqual(
            create["status"]["new"],
            str(h.status),
        )
        self.assertEqual(
            create["type"]["old"],
            "",
        )
        self.assertEqual(
            create["type"]["new"],
            str(h.type),
        )
        self.assertEqual(
            create["cash_book_id"]["old"],
            "",
        )
        self.assertEqual(
            create["cash_book_id"]["new"],
            str(h.cash_book_id),
        )
        self.assertEqual(
            create["supplier_id"]["old"],
            "",
        )
        self.assertEqual(
            create["supplier_id"]["new"],
            str(h.supplier_id),
        )
        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "header"
        )
        update = all_changes[1]
        self.assertEqual(
            update["ref"]["old"],
            "123",
        )
        self.assertEqual(
            update["ref"]["new"],
            h.ref,
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "header"
        )

    def test_lines(self):
        # same as above except for change a line
        # above has no lines
        cash_book = CashBook.objects.create(
            nominal=None,
            name="current"
        )
        supplier = Supplier.objects.create(
            code="1",
            name="2",
            email="3"
        )
        h = PurchaseHeader.objects.create(
            type="pi",  # payment
            date=date.today(),
            goods=100,
            vat=20,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period=self.period
        )

        nominal = Nominal.objects.create(
            name="something",
            parent=None
        )
        vat_code = Vat.objects.create(
            code="1",
            name="2",
            rate=20
        )
        l = PurchaseLine.objects.create(
            nominal=nominal,
            goods=100,
            vat=20,
            vat_code=vat_code,
            description="123",
            line_no=1,
            header=h
        )
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            1
        )
        h.ref = "1234"  # update the header
        h.save()
        h.refresh_from_db()
        l.description = "12345"
        l.save()
        l.refresh_from_db()
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            2
        )
        audit_transaction = AuditTransaction(
            h, PurchaseHeader, PurchaseLine, PurchaseMatching)
        self.assertEqual(
            len(audit_transaction.audit_header_history),
            2
        )
        self.assertEqual(
            len(audit_transaction.audit_lines_history),
            2
        )
        self.assertEqual(
            len(audit_transaction.audit_matches_history),
            0
        )
        all_changes = audit_transaction.get_historical_changes()
        self.assertEqual(
            len(all_changes),
            4
        )
        self.assertTrue(
            all_changes[0]["meta"]["AUDIT_date"] < all_changes[1]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[1]["meta"]["AUDIT_date"] < all_changes[2]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[2]["meta"]["AUDIT_date"] < all_changes[3]["meta"]["AUDIT_date"]
        )

        create = all_changes[0]
        self.assertEqual(
            create["id"]["old"],
            "",
        )
        self.assertEqual(
            create["id"]["new"],
            str(h.id),
        )
        self.assertEqual(
            create["ref"]["old"],
            "",
        )
        self.assertEqual(
            create["ref"]["new"],
            "123",
        )
        self.assertEqual(
            create["goods"]["old"],
            "",
        )
        self.assertEqual(
            create["goods"]["new"],
            str(h.goods),
        )
        self.assertEqual(
            create["vat"]["old"],
            "",
        )
        self.assertEqual(
            create["vat"]["new"],
            str(h.vat),
        )
        self.assertEqual(
            create["total"]["old"],
            "",
        )
        self.assertEqual(
            create["total"]["new"],
            str(h.total),
        )
        self.assertEqual(
            create["paid"]["old"],
            "",
        )
        self.assertEqual(
            create["paid"]["new"],
            str(h.paid),
        )
        self.assertEqual(
            create["due"]["old"],
            "",
        )
        self.assertEqual(
            create["due"]["new"],
            str(h.due),
        )
        self.assertEqual(
            create["date"]["old"],
            "",
        )
        self.assertEqual(
            create["date"]["new"],
            str(h.date),
        )
        self.assertEqual(
            create["due_date"]["old"],
            "",
        )
        self.assertEqual(
            create["due_date"]["new"],
            str(h.due_date),
        )
        self.assertEqual(
            create["period_id"]["old"],
            "",
        )
        self.assertEqual(
            create["period_id"]["new"],
            str(self.period.pk),
        )
        self.assertEqual(
            create["status"]["old"],
            "",
        )
        self.assertEqual(
            create["status"]["new"],
            str(h.status),
        )
        self.assertEqual(
            create["type"]["old"],
            "",
        )
        self.assertEqual(
            create["type"]["new"],
            str(h.type),
        )
        self.assertEqual(
            create["cash_book_id"]["old"],
            "",
        )
        self.assertEqual(
            create["cash_book_id"]["new"],
            str(h.cash_book_id),
        )
        self.assertEqual(
            create["supplier_id"]["old"],
            "",
        )
        self.assertEqual(
            create["supplier_id"]["new"],
            str(h.supplier_id),
        )
        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "header"
        )
        update = all_changes[2]
        self.assertEqual(
            update["ref"]["old"],
            "123",
        )
        self.assertEqual(
            update["ref"]["new"],
            h.ref,
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "header"
        )

        # now for the line change
        create = all_changes[1]
        self.assertEqual(
            create["id"]["old"],
            "",
        )
        self.assertEqual(
            create["id"]["new"],
            str(l.id),
        )
        self.assertEqual(
            create["description"]["old"],
            "",
        )
        self.assertEqual(
            create["description"]["new"],
            "123",
        )
        self.assertEqual(
            create["goods"]["old"],
            ""
        )
        self.assertEqual(
            create["goods"]["new"],
            str(l.goods),
        )
        self.assertEqual(
            create["vat"]["old"],
            "",
        )
        self.assertEqual(
            create["vat"]["new"],
            str(l.vat),
        )
        self.assertEqual(
            create["line_no"]["old"],
            "",
        )
        self.assertEqual(
            create["line_no"]["new"],
            str(l.line_no),
        )
        self.assertEqual(
            create["nominal_id"]["old"],
            "",
        )
        self.assertEqual(
            create["nominal_id"]["new"],
            str(l.nominal.pk),
        )
        self.assertEqual(
            create["vat_code_id"]["old"],
            "",
        )
        self.assertEqual(
            create["vat_code_id"]["new"],
            str(l.vat_code.pk),
        )
        self.assertEqual(
            create["header_id"]["old"],
            "",
        )
        self.assertEqual(
            create["header_id"]["new"],
            str(l.header.pk),
        )

        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "line"
        )

        update = all_changes[3]
        self.assertEqual(
            update["description"]["old"],
            "123",
        )
        self.assertEqual(
            update["description"]["new"],
            l.description,
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "line"
        )

    def test_matching(self):
        # same as above except for change a line
        # above has no lines
        cash_book = CashBook.objects.create(
            nominal=None,
            name="current"
        )
        supplier = Supplier.objects.create(
            code="1",
            name="2",
            email="3"
        )
        to_match_against = PurchaseHeader.objects.create(
            type="pi",  # payment
            date=date.today(),
            goods=-100,
            vat=-20,
            total=-120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period=self.period
        )
        h = PurchaseHeader.objects.create(
            type="pi",  # payment
            date=date.today(),
            goods=100,
            vat=20,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period=self.period
        )
        nominal = Nominal.objects.create(
            name="something",
            parent=None
        )
        vat_code = Vat.objects.create(
            code="1",
            name="2",
            rate=20
        )
        l = PurchaseLine.objects.create(
            nominal=nominal,
            goods=100,
            vat=20,
            vat_code=vat_code,
            description="123",
            line_no=1,
            header=h
        )
        match = PurchaseMatching.objects.create(
            matched_by=h,
            matched_to=to_match_against,
            period=self.period,
            value=-100
        )
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            2
        )
        self.assertEqual(
            len(PurchaseMatching.history.all()),
            1
        )
        h.ref = "1234"  # update the header
        h.save()
        h.refresh_from_db()

        l.description = "12345"
        l.save()
        l.refresh_from_db()

        match.value = -120
        match.save()
        match.refresh_from_db()

        audit_transaction = AuditTransaction(
            h, PurchaseHeader, PurchaseLine, PurchaseMatching)
        self.assertEqual(
            len(audit_transaction.audit_header_history),
            2
        )
        self.assertEqual(
            len(audit_transaction.audit_lines_history),
            2
        )
        self.assertEqual(
            len(audit_transaction.audit_matches_history),
            2
        )
        all_changes = audit_transaction.get_historical_changes()
        self.assertEqual(
            len(all_changes),
            6
        )

        self.assertTrue(
            all_changes[0]["meta"]["AUDIT_date"] <= all_changes[1]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[1]["meta"]["AUDIT_date"] <= all_changes[2]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[2]["meta"]["AUDIT_date"] <= all_changes[3]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[3]["meta"]["AUDIT_date"] <= all_changes[4]["meta"]["AUDIT_date"]
        )
        self.assertTrue(
            all_changes[4]["meta"]["AUDIT_date"] <= all_changes[5]["meta"]["AUDIT_date"]
        )

        create = all_changes[0]
        self.assertEqual(
            create["id"]["old"],
            "",
        )
        self.assertEqual(
            create["id"]["new"],
            str(h.id),
        )
        self.assertEqual(
            create["ref"]["old"],
            "",
        )
        self.assertEqual(
            create["ref"]["new"],
            "123",
        )
        self.assertEqual(
            create["goods"]["old"],
            "",
        )
        self.assertEqual(
            create["goods"]["new"],
            str(h.goods),
        )
        self.assertEqual(
            create["vat"]["old"],
            "",
        )
        self.assertEqual(
            create["vat"]["new"],
            str(h.vat),
        )
        self.assertEqual(
            create["total"]["old"],
            "",
        )
        self.assertEqual(
            create["total"]["new"],
            str(h.total),
        )
        self.assertEqual(
            create["paid"]["old"],
            "",
        )
        self.assertEqual(
            create["paid"]["new"],
            str(h.paid),
        )
        self.assertEqual(
            create["due"]["old"],
            "",
        )
        self.assertEqual(
            create["due"]["new"],
            str(h.due),
        )
        self.assertEqual(
            create["date"]["old"],
            "",
        )
        self.assertEqual(
            create["date"]["new"],
            str(h.date),
        )
        self.assertEqual(
            create["due_date"]["old"],
            "",
        )
        self.assertEqual(
            create["due_date"]["new"],
            str(h.due_date),
        )
        self.assertEqual(
            create["period_id"]["old"],
            "",
        )
        self.assertEqual(
            create["period_id"]["new"],
            str(self.period.pk),
        )
        self.assertEqual(
            create["status"]["old"],
            "",
        )
        self.assertEqual(
            create["status"]["new"],
            str(h.status),
        )
        self.assertEqual(
            create["type"]["old"],
            "",
        )
        self.assertEqual(
            create["type"]["new"],
            str(h.type),
        )
        self.assertEqual(
            create["cash_book_id"]["old"],
            "",
        )
        self.assertEqual(
            create["cash_book_id"]["new"],
            str(h.cash_book_id),
        )
        self.assertEqual(
            create["supplier_id"]["old"],
            "",
        )
        self.assertEqual(
            create["supplier_id"]["new"],
            str(h.supplier_id),
        )
        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "header"
        )
        update = all_changes[3]
        self.assertEqual(
            update["ref"]["old"],
            "123",
        )
        self.assertEqual(
            update["ref"]["new"],
            h.ref,
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "header"
        )

        # now for the line change
        create = all_changes[1]
        self.assertEqual(
            create["id"]["old"],
            "",
        )
        self.assertEqual(
            create["id"]["new"],
            str(l.id),
        )
        self.assertEqual(
            create["description"]["old"],
            "",
        )
        self.assertEqual(
            create["description"]["new"],
            "123",
        )
        self.assertEqual(
            create["goods"]["old"],
            ""
        )
        self.assertEqual(
            create["goods"]["new"],
            str(l.goods),
        )
        self.assertEqual(
            create["vat"]["old"],
            "",
        )
        self.assertEqual(
            create["vat"]["new"],
            str(l.vat),
        )
        self.assertEqual(
            create["line_no"]["old"],
            "",
        )
        self.assertEqual(
            create["line_no"]["new"],
            str(l.line_no),
        )
        self.assertEqual(
            create["nominal_id"]["old"],
            "",
        )
        self.assertEqual(
            create["nominal_id"]["new"],
            str(l.nominal.pk),
        )
        self.assertEqual(
            create["vat_code_id"]["old"],
            "",
        )
        self.assertEqual(
            create["vat_code_id"]["new"],
            str(l.vat_code.pk),
        )
        self.assertEqual(
            create["header_id"]["old"],
            "",
        )
        self.assertEqual(
            create["header_id"]["new"],
            str(l.header.pk),
        )
        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "line"
        )

        update = all_changes[4]
        self.assertEqual(
            update["description"]["old"],
            "123",
        )
        self.assertEqual(
            update["description"]["new"],
            l.description,
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "line"
        )

        create = all_changes[2]
        self.assertEqual(
            create["matched_by_id"]["old"],
            "",
        )
        self.assertEqual(
            create["matched_by_id"]["new"],
            str(match.matched_by_id),
        )
        self.assertEqual(
            create["matched_to_id"]["old"],
            "",
        )
        self.assertEqual(
            create["matched_to_id"]["new"],
            str(match.matched_to_id),
        )
        self.assertEqual(
            create["value"]["old"],
            "",
        )
        self.assertEqual(
            create["value"]["new"],
            "-100.00",
        )
        self.assertEqual(
            create["period_id"]["old"],
            "",
        )
        self.assertEqual(
            create["period_id"]["new"],
            str(self.period.pk),
        )
        self.assertEqual(
            create["meta"]["AUDIT_action"],
            "Create"
        )
        self.assertEqual(
            create["meta"]["transaction_aspect"],
            "match"
        )

        update = all_changes[5]
        self.assertEqual(
            update["value"]["old"],
            "-100.00"
        )
        self.assertEqual(
            update["value"]["new"],
            "-120.00"
        )
        self.assertEqual(
            update["meta"]["AUDIT_action"],
            "Update"
        )
        self.assertEqual(
            update["meta"]["transaction_aspect"],
            "match"
        )

from datetime import date

from django.test import TestCase

from accountancy.helpers import AuditTransaction, Period
from cashbook.models import CashBook
from nominals.models import Nominal
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)
from vat.models import Vat


class AuditTransactionTest(TestCase):
    """
    Test with PL header, line, matching
    """

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
            type="pp", # payment
            date=date.today(),
            goods=120,
            vat=0,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period="202006"
        )
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            1
        )
        h.ref = "1234" # update the header
        h.save()
        h.refresh_from_db()
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            2
        )
        audit_transaction = AuditTransaction(h, PurchaseHeader, PurchaseLine, PurchaseMatching)    
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
            create["period"]["old"],
            "",
        )
        self.assertEqual(
            create["period"]["new"],
            str(h.period),
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
            type="pi", # payment
            date=date.today(),
            goods=100,
            vat=20,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period="202006"
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
        h.ref = "1234" # update the header
        h.save()
        h.refresh_from_db()
        l.description = "12345"
        l.save()
        l.refresh_from_db()
        self.assertEqual(
            len(PurchaseHeader.history.all()),
            2
        )
        audit_transaction = AuditTransaction(h, PurchaseHeader, PurchaseLine, PurchaseMatching)    
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
            create["period"]["old"],
            "",
        )
        self.assertEqual(
            create["period"]["new"],
            str(h.period),
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
            type="pi", # payment
            date=date.today(),
            goods=-100,
            vat=-20,
            total=-120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period="202006"            
        )
        h = PurchaseHeader.objects.create(
            type="pi", # payment
            date=date.today(),
            goods=100,
            vat=20,
            total=120,
            ref="123",
            cash_book=cash_book,
            supplier=supplier,
            paid=0,
            due=0,
            period="202006"
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
            period="202006",
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
        h.ref = "1234" # update the header
        h.save()
        h.refresh_from_db()

        l.description = "12345"
        l.save()
        l.refresh_from_db()

        match.value = -120
        match.save()
        match.refresh_from_db()

        audit_transaction = AuditTransaction(h, PurchaseHeader, PurchaseLine, PurchaseMatching)    
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
            create["period"]["old"],
            "",
        )
        self.assertEqual(
            create["period"]["new"],
            str(h.period),
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
            create["period"]["old"],
            "",
        )
        self.assertEqual(
            create["period"]["new"],
            str(match.period),
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


class PeriodTestGeneral(TestCase):

    def test_equality_with_same_objects(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertTrue(
            p1 == p2
        )

    def test_equality_when_not_both_objects_1(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p1 == p2
        )

    def test_equality_when_not_both_objects_2(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p2 == p1
        )

    def test_inequality(self):
        p1 = Period("202007")
        p2 = Period("202006")
        self.assertFalse(
            p1 == p2
        )

    def test_less_than_or_equal_to_with_same_objects_1(self):
        p1 = Period("202007")
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_same_objects_2(self):
        p1 = Period("202006")
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_same_objects_3(self):
        p1 = Period("202008")
        p2 = Period("202007")
        self.assertFalse(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_1(self):
        p1 = Period("202007")
        p2 = "202007"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_2(self):
        p1 = Period("202007")
        p2 = "202008"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_3(self):
        p1 = Period("202008")
        p2 = "202007"
        self.assertFalse(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_4(self):
        p1 = "202007"
        p2 = Period("202007")
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_5(self):
        p1 = "202007"
        p2 = "202008"
        self.assertTrue(
            p1 <= p2
        )

    def test_less_than_or_equal_to_with_different_objects_6(self):
        p1 = "202008"
        p2 = Period("202007")
        self.assertFalse(
            p1 <= p2
        )

    def test_str(self):
        p = Period("202007")
        self.assertEqual(
            str(p),
            "202007"
        )


class PeriodTestForFYStart(TestCase):
    """
    Here the period added to is always 202001
    """

    def test_sub_0(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 0,
            "202001"
        )

    def test_sub_1(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 1,
            "201912"
        )

    def test_sub_2(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 2,
            "201911"
        )

    def test_sub_3(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 3,
            "201910"
        )

    def test_sub_4(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 4,
            "201909"
        )

    def test_sub_5(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 5,
            "201908"
        )

    def test_sub_6(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 6,
            "201907"
        )

    def test_sub_7(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 7,
            "201906"
        )

    def test_sub_8(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 8,
            "201905"
        )

    def test_sub_9(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 9,
            "201904"
        )

    def test_sub_10(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 10,
            "201903"
        )

    def test_sub_11(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 11,
            "201902"
        )

    def test_sub_12(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 12,
            "201901"
        )

    def test_sub_13(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 13,
            "201812"
        )

    def test_sub_48(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p - 48,
            "201601"
        )

    def test_add_0(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 0,
            "202001"
        )

    def test_add_1(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 1,
            "202002"
        )

    def test_add_2(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 2,
            "202003"
        )

    def test_add_3(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 3,
            "202004"
        )

    def test_add_4(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 4,
            "202005"
        )

    def test_add_5(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 5,
            "202006"
        )

    def test_add_6(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 6,
            "202007"
        )

    def test_add_7(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 7,
            "202008"
        )

    def test_add_8(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 8,
            "202009"
        )

    def test_add_9(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 9,
            "202010"
        )

    def test_add_10(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 10,
            "202011"
        )

    def test_add_11(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 11,
            "202012"
        )

    def test_add_12(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 12,
            "202101"
        )

    def test_add_13(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 13,
            "202102"
        )

    def test_add_48(self):
        period = "202001"
        p = Period(period)
        self.assertEqual(
            p + 48,
            "202401"
        )


class PeriodTestForFYEnd(TestCase):
    """
    Here the period added to is always 202012
    """

    def test_sub_0(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 0,
            "202012"
        )

    def test_sub_1(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 1,
            "202011"
        )

    def test_sub_2(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 2,
            "202010"
        )

    def test_sub_3(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 3,
            "202009"
        )

    def test_sub_4(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 4,
            "202008"
        )

    def test_sub_5(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 5,
            "202007"
        )

    def test_sub_6(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 6,
            "202006"
        )

    def test_sub_7(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 7,
            "202005"
        )

    def test_sub_8(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 8,
            "202004"
        )

    def test_sub_9(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 9,
            "202003"
        )

    def test_sub_10(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 10,
            "202002"
        )

    def test_sub_11(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 11,
            "202001"
        )

    def test_sub_12(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 12,
            "201912"
        )

    def test_sub_13(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 13,
            "201911"
        )

    def test_sub_48(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p - 48,
            "201612"
        )

    def test_add_0(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 0,
            "202012"
        )

    def test_add_1(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 1,
            "202101"
        )

    def test_add_2(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 2,
            "202102"
        )

    def test_add_3(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 3,
            "202103"
        )

    def test_add_4(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 4,
            "202104"
        )

    def test_add_5(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 5,
            "202105"
        )

    def test_add_6(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 6,
            "202106"
        )

    def test_add_7(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 7,
            "202107"
        )

    def test_add_8(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 8,
            "202108"
        )

    def test_add_9(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 9,
            "202109"
        )

    def test_add_10(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 10,
            "202110"
        )

    def test_add_11(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 11,
            "202111"
        )

    def test_add_12(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 12,
            "202112"
        )

    def test_add_13(self):
        period = "202012"
        p = Period(period)
        self.assertEqual(
            p + 13,
            "202201"
        )

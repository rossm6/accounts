from datetime import date, datetime, timedelta

from controls.models import FinancialYear, Period
from django.test import TestCase
from nominals.models import (Nominal, NominalHeader, NominalLine,
                             NominalTransaction)

DATE_INPUT_FORMAT = '%d-%m-%Y'
MODEL_DATE_INPUT_FORMAT = '%Y-%m-%d'

class NonAuditQuerySetTests(TestCase):

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
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))

    def test_bulk_update(self):
        nominal = Nominal(name="duh")
        nominal.save()
        tran = NominalTransaction(
            module="NL",
            header=1,
            line=1,
            value=0,
            date=date.today(),
            period=self.period,
            field="t",
            nominal=nominal
        )
        tran.save()
        new_period = Period.objects.create(fy=self.fy, fy_and_period="202002", period="02", month_start=date(2020,2,29))
        tran.period = new_period
        NominalTransaction.objects.bulk_update([tran])
        tran.refresh_from_db()
        self.assertEqual(
            tran.period,
            new_period
        )


class AuditQuerySetTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.date = datetime.now().strftime(DATE_INPUT_FORMAT)
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(DATE_INPUT_FORMAT)
        cls.model_date = datetime.now().strftime(MODEL_DATE_INPUT_FORMAT)
        cls.model_due_date = (datetime.now() + timedelta(days=31)
                        ).strftime(MODEL_DATE_INPUT_FORMAT)
        fy = FinancialYear.objects.create(financial_year=2020)
        cls.period = Period.objects.create(fy=fy, period="01", fy_and_period="202001", month_start=date(2020,1,31))

    def test_audited_bulk_create_empty(self):
        # check it handles empty list
        NominalHeader.objects.audited_bulk_create([])
        self.assertEqual(
            len(
                NominalHeader.objects.all()
            ),
            0
        )
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            0
        )

    def test_audited_bulk_create(self):
        d = date.today()
        h = NominalHeader(
            ref="1",
            period=self.period,
            date=d,
        )
        objs = [h]
        NominalHeader.objects.audited_bulk_create(objs)
        headers = NominalHeader.objects.all()
        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
        self.assertEqual(
            header.ref,
            "1"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.date,
            d
        )
        audits = NominalHeader.history.all()
        self.assertEqual(
            len(audits),
            1
        )

    def test_audited_bulk_line_update_empty(self):
        NominalHeader.objects.audited_bulk_update([], ["ref"])
        self.assertEqual(
            len(
                NominalHeader.objects.all()
            ),
            0
        )
        self.assertEqual(
            len(
                NominalHeader.history.all()
            ),
            0
        )

    def test_audited_bulk_update_with_fields(self):
        d = date.today()
        h = NominalHeader(
            ref="1",
            period=self.period,
            date=d,
        )
        h.save()
        h.ref = "2"
        objs = [h]
        NominalHeader.objects.audited_bulk_update(objs, ["ref"])
        headers = NominalHeader.objects.all()
        self.assertEqual(
            len(headers),
            1
        )
        header = headers[0]
        self.assertEqual(
            header.ref,
            "2"
        )
        self.assertEqual(
            header.period,
            self.period
        )
        self.assertEqual(
            header.date,
            d
        )
        audits = NominalHeader.history.all()
        self.assertEqual(
            len(audits),
            2
        )

    def test_audited_bulk_update_without_fields(self):
        d = date.today()
        h = NominalHeader(
            ref="1",
            period=self.period,
            date=d,
        )
        h.save()
        nominal = Nominal(name="duh")
        nominal.save()
        l = NominalLine(
            header=h,
            line_no=1,
            description="1",
            nominal=nominal,
            type="g"
        )
        l.save()
        l.description = "2"
        NominalLine.objects.audited_bulk_update([l])
        l.refresh_from_db()
        self.assertEqual(
            l.description,
            "2"
        )
        self.assertEqual(
            len(
                NominalLine.history.all()
            ),
            2
        )

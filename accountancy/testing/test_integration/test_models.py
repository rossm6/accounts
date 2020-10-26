from datetime import date

from django.test import TestCase
from nominals.models import (Nominal, NominalHeader, NominalLine,
                             NominalTransaction)

PERIOD = "202007"


class NonAuditQuerySetTests(TestCase):

    def test_bulk_update(self):
        nominal = Nominal(name="duh")
        nominal.save()
        tran = NominalTransaction(
            module="NL",
            header=1,
            line=1,
            value=0,
            date=date.today(),
            period=PERIOD,
            field="t",
            nominal=nominal
        )
        tran.save()
        tran.period = "202008"
        NominalTransaction.objects.bulk_update([tran])
        tran.refresh_from_db()
        self.assertEqual(
            tran.period,
            "202008"
        )


class AuditQuerySetTests(TestCase):

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
            period=PERIOD,
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
            PERIOD
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
            period=PERIOD,
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
            PERIOD
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
            period=PERIOD,
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
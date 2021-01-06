from datetime import date

from controls.models import FinancialYear, ModuleSettings, Period
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import TestCase
from nominals.models import Nominal, NominalHeader, NominalTransaction
from nominals.views import FinaliseFY


class RollbackFYTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # 2019
        cls.fy_2019 = fy_2019 = FinancialYear.objects.create(
            financial_year=2019, number_of_periods=12)
        cls.p_201901 = p_201901 = Period.objects.create(
            fy=fy_2019, period="01", fy_and_period="201901", month_start=date(2019, 1, 31))
        # 2020
        cls.fy_2020 = fy_2020 = FinancialYear.objects.create(
            financial_year=2020, number_of_periods=12)
        cls.p_202001 = p_202001 = Period.objects.create(
            fy=fy_2020, period="01", fy_and_period="202001", month_start=date(2020, 1, 31))
        # 2021
        cls.fy_2021 = fy_2021 = FinancialYear.objects.create(
            financial_year=2021, number_of_periods=12)
        cls.p_202101 = p_202101 = Period.objects.create(
            fy=fy_2021, period="01", fy_and_period="202101", month_start=date(2021, 1, 31))

        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.url = reverse("nominals:rollback_fy")

        # ASSETS
        assets = Nominal.objects.create(name="Assets", type="b")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets", type="b")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account", type="b")
        cls.debtors_nominal = Nominal.objects.create(
            parent=current_assets, name="Trade Debtors", type="b")

        # LIABILITIES
        cls.liabilities = liabilities = Nominal.objects.create(
            name="Liabilities", type="b"
        )
        cls.current_liabilities = current_liabilities = Nominal.objects.create(
            name="Current Liabilities", type="b", parent=liabilities
        )
        cls.vat_output = vat_output = Nominal.objects.create(
            name="Vat Output", type="b", parent=current_liabilities
        )

    def test(self):
        # 2019
        header_1 = NominalHeader.objects.create(
            date=date.today(), # does not matter
            ref="1",
            period=self.p_201901,
            status="c",
            type="nbf",
            vat_type=None
        )
        bf_2019_1 = NominalTransaction.objects.create(
            module="NL",
            header=header_1.pk,
            line=1,
            date=date.today(),
            ref="YEAR END 2018",
            period=self.p_201901,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=1000
        )
        bf_2019_2 = NominalTransaction.objects.create(
            module="NL",
            header=header_1.pk,
            line=2,
            date=date.today(),
            ref="YEAR END 2018",
            period=self.p_201901,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )
        header_2 = NominalHeader.objects.create(
            date=date.today(), # does not matter
            ref="2",
            period=self.p_202001,
            status="c",
            type="nbf",
            vat_type=None
        )
        # 2020
        bf_2020_1 = NominalTransaction.objects.create(
            module="NL",
            header=header_2.pk,
            line=1,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=1000
        )
        bf_2020_2 = NominalTransaction.objects.create(
            module="NL",
            header=header_2.pk,
            line=2,
            date=date.today(),
            ref="YEAR END 2019",
            period=self.p_202001,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )
        header_3 = NominalHeader.objects.create(
            date=date.today(), # does not matter
            ref="3",
            period=self.p_202101,
            status="c",
            type="nbf",
            vat_type=None
        )
        # 2021
        bf_2021_1 = NominalTransaction.objects.create(
            module="NL",
            header=header_3.pk,
            line=1,
            date=date.today(),
            ref="YEAR END 2020",
            period=self.p_202101,
            field="t",
            type="nbf",
            nominal=self.bank_nominal,
            value=1000
        )
        bf_2021_2 = NominalTransaction.objects.create(
            module="NL",
            header=header_3.pk,
            line=2,
            date=date.today(),
            ref="YEAR END 2020",
            period=self.p_202101,
            field="t",
            type="nbf",
            nominal=self.vat_output,
            value=-1000
        )

        response = self.client.post(self.url, {"financial_year": self.fy_2019.pk})
        # rollback to 2019 means deleting bf in 2020, 2021, 2022 etc
        # the view will add 1 to the FY entered into the form
        # this is then passed to NominalTransaction.objects.rollback_fy
        # so in this example 2020 (= 2019 + 1) is passed to the function
        # which means bfs in 2020 and after all get deleted
        # posting periods remain as they were though
        self.assertEqual(
            response.status_code,
            302
        )
        bfs = NominalTransaction.objects.filter(module="NL").filter(type="nbf").order_by("line")
        self.assertEqual(
            len(bfs),
            2
        )
        self.assertEqual(
            bfs[0],
            bf_2019_1
        )
        self.assertEqual(
            bfs[1],
            bf_2019_2
        )
        headers = NominalHeader.objects.all()
        self.assertEqual(
            len(headers),
            1
        )
        self.assertEqual(
            headers[0],
            header_1
        )
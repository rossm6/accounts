from datetime import date

from controls.models import FinancialYear, Period
from django.contrib.auth import get_user_model
from django.test import TestCase
from nominals.models import Nominal, NominalHeader, NominalTransaction


class CarryForwardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy_2019 = fy = FinancialYear.objects.create(financial_year=2019)
        cls.period_201901 = Period.objects.create(
            fy=fy, period="01", fy_and_period="201901", month_end=date(2019, 1, 31))
        cls.fy_2020 = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period_202001 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))
        cls.fy_2021 = fy = FinancialYear.objects.create(financial_year=2021)
        cls.period_202101 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202101", month_end=date(2021, 1, 31))

        # P/L
        cls.revenue_1 = revenue_1 = Nominal.objects.create(
            name="revenue", type="pl")
        cls.revenue_2 = revenue_2 = Nominal.objects.create(
            name="revenue", type="pl", parent=revenue_1)
        cls.sales = sales = Nominal.objects.create(
            name="sales", type="pl", parent=revenue_2)

        # Expenses
        cls.expenses_1 = expenses_1 = Nominal.objects.create(
            name="expenses", type="pl")
        cls.expenses_2 = expenses_2 = Nominal.objects.create(
            name="expenses", type="pl", parent=expenses_1)
        cls.staff = staff = Nominal.objects.create(
            name="staff", type="pl", parent=expenses_2)

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

        # EQUITY
        cls.equity_1 = equity_1 = Nominal.objects.create(
            name="Equity", type="b")
        cls.equity_2 = equity_2 = Nominal.objects.create(
            name="Equity", type="b", parent=equity_1)
        cls.retained_earnings = retained_earnings = Nominal.objects.create(
            name="Retained Earnings",
            type="b",
            parent=equity_2
        )

    def test_when_there_are_no_transactions(self):
        NominalTransaction.objects.carry_forward(
            self.fy_2019, self.period_202001)
        self.assertEqual(
            len(NominalTransaction.objects.all()),
            0
        )

    def test_balance_sheet_only_trans(self):
        # here we also test that the header is incremented
        # because there is a nom tran with module = NL already
        t1 = NominalTransaction.objects.create(
            module="NL",
            header=2,
            line=1,
            ref="1",
            period=self.period_201901,
            field="g",
            type="nj",
            nominal=self.bank_nominal,
            value=1000,
            date=date.today()
        )
        t2 = NominalTransaction.objects.create(
            module="NL",
            header=2,
            line=2,
            ref="1",
            period=self.period_201901,
            field="g",
            type="nj",
            nominal=self.debtors_nominal,
            value=-1000,
            date=date.today()
        )
        NominalTransaction.objects.carry_forward(
            self.fy_2019, self.period_202001)
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            4
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )

        bank_bf = nom_trans[2]
        self.assertEqual(
            bank_bf.module,
            "NL"
        )
        self.assertEqual(
            bank_bf.header,
            3
        )
        self.assertEqual(
            bank_bf.line,
            1
        )
        self.assertEqual(
            bank_bf.date,
            date.today()
        )
        self.assertEqual(
            bank_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            bank_bf.period,
            self.period_202001
        )
        self.assertEqual(
            bank_bf.type,
            "nbf"
        )
        self.assertEqual(
            bank_bf.field,
            "t"
        )
        self.assertEqual(
            bank_bf.value,
            t1.value
        )
        self.assertEqual(
            bank_bf.nominal,
            self.bank_nominal
        )

        self.assertEqual(
            nom_trans[1],
            t2
        )
        debtor_bf = nom_trans[3]

        self.assertEqual(
            debtor_bf.module,
            "NL"
        )
        self.assertEqual(
            debtor_bf.header,
            3
        )
        self.assertEqual(
            debtor_bf.line,
            2
        )
        self.assertEqual(
            debtor_bf.date,
            date.today()
        )
        self.assertEqual(
            debtor_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            debtor_bf.period,
            self.period_202001
        )
        self.assertEqual(
            debtor_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtor_bf.field,
            "t"
        )
        self.assertEqual(
            debtor_bf.value,
            t2.value
        )
        self.assertEqual(
            debtor_bf.nominal,
            self.debtors_nominal
        )

    def test_when_profit_and_loss_is_zero(self):
        t1 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            ref="1",
            period=self.period_201901,
            field="g",
            type="nj",
            nominal=self.staff,
            value=1000,
            date=date.today()
        )
        t2 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=2,
            ref="1",
            period=self.period_201901,
            field="g",
            type="nj",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        NominalTransaction.objects.carry_forward(
            self.fy_2019, self.period_202001)
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )

    def test_first_year_end_with_pl_and_bal_trans(self):
        # transactions in PL and Balance Sheet
        # test here that header = 1 because nom trans with module = NL
        # do not exist already
        t1 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=1,
            ref="1",
            period=self.period_201901,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t2 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=2,
            ref="1",
            period=self.period_201901,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t3 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=3,
            ref="1",
            period=self.period_201901,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )
        t4 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=1,
            ref="2",
            period=self.period_201901,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t5 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=2,
            ref="2",
            period=self.period_201901,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t6 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=3,
            ref="2",
            period=self.period_201901,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )
        NominalTransaction.objects.carry_forward(
            self.fy_2019, self.period_202001)
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            9
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )
        self.assertEqual(
            nom_trans[2],
            t3
        )
        self.assertEqual(
            nom_trans[3],
            t4
        )
        self.assertEqual(
            nom_trans[4],
            t5
        )
        self.assertEqual(
            nom_trans[5],
            t6
        )

        for bf in nom_trans[6:]:
            if bf.nominal == self.vat_output:
                vat_output_bf = bf
            elif bf.nominal == self.debtors_nominal:
                debtors_bf = bf
            elif bf.nominal == self.retained_earnings:
                retained_earnings_bf = bf

        lines = [vat_output_bf.line, debtors_bf.line,
                 retained_earnings_bf.line]
        lines.sort()

        self.assertEqual(
            [1, 2, 3],
            lines
        )

        # 1
        self.assertEqual(
            debtors_bf.module,
            "NL"
        )
        self.assertEqual(
            debtors_bf.header,
            1
        )
        self.assertEqual(
            debtors_bf.date,
            date.today()
        )
        self.assertEqual(
            debtors_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            debtors_bf.period,
            self.period_202001
        )
        self.assertEqual(
            debtors_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtors_bf.field,
            "t"
        )
        self.assertEqual(
            debtors_bf.value,
            2400
        )
        self.assertEqual(
            debtors_bf.nominal,
            self.debtors_nominal
        )

        # 2
        self.assertEqual(
            vat_output_bf.module,
            "NL"
        )
        self.assertEqual(
            vat_output_bf.header,
            1
        )
        self.assertEqual(
            vat_output_bf.date,
            date.today()
        )
        self.assertEqual(
            vat_output_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            vat_output_bf.period,
            self.period_202001
        )
        self.assertEqual(
            vat_output_bf.type,
            "nbf"
        )
        self.assertEqual(
            vat_output_bf.field,
            "t"
        )
        self.assertEqual(
            vat_output_bf.value,
            -400
        )
        self.assertEqual(
            vat_output_bf.nominal,
            self.vat_output
        )

        # 3
        self.assertEqual(
            retained_earnings_bf.module,
            "NL"
        )
        self.assertEqual(
            retained_earnings_bf.header,
            1
        )
        self.assertEqual(
            retained_earnings_bf.date,
            date.today()
        )
        self.assertEqual(
            retained_earnings_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            retained_earnings_bf.period,
            self.period_202001
        )
        self.assertEqual(
            retained_earnings_bf.type,
            "nbf"
        )
        self.assertEqual(
            retained_earnings_bf.field,
            "t"
        )
        self.assertEqual(
            retained_earnings_bf.value,
            -2000
        )
        self.assertEqual(
            retained_earnings_bf.nominal,
            self.retained_earnings
        )

    def test_second_fy_end(self):
        # 2019 trans -- first FY
        t1 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=1,
            ref="1",
            period=self.period_201901,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t2 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=2,
            ref="1",
            period=self.period_201901,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t3 = NominalTransaction.objects.create(
            module="SL",
            header=1,
            line=3,
            ref="1",
            period=self.period_201901,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )
        t4 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=1,
            ref="2",
            period=self.period_201901,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t5 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=2,
            ref="2",
            period=self.period_201901,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t6 = NominalTransaction.objects.create(
            module="SL",
            header=2,
            line=3,
            ref="2",
            period=self.period_201901,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )
        NominalTransaction.objects.carry_forward(
            self.fy_2019, self.period_202001)
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            9
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )
        self.assertEqual(
            nom_trans[2],
            t3
        )
        self.assertEqual(
            nom_trans[3],
            t4
        )
        self.assertEqual(
            nom_trans[4],
            t5
        )
        self.assertEqual(
            nom_trans[5],
            t6
        )

        for bf in nom_trans[6:]:
            if bf.nominal == self.vat_output:
                vat_output_bf = bf
            elif bf.nominal == self.debtors_nominal:
                debtors_bf = bf
            elif bf.nominal == self.retained_earnings:
                retained_earnings_bf = bf

        lines = [vat_output_bf.line, debtors_bf.line,
                 retained_earnings_bf.line]
        lines.sort()

        self.assertEqual(
            [1, 2, 3],
            lines
        )

        # 1
        self.assertEqual(
            debtors_bf.module,
            "NL"
        )
        self.assertEqual(
            debtors_bf.header,
            1
        )
        self.assertEqual(
            debtors_bf.date,
            date.today()
        )
        self.assertEqual(
            debtors_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            debtors_bf.period,
            self.period_202001
        )
        self.assertEqual(
            debtors_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtors_bf.field,
            "t"
        )
        self.assertEqual(
            debtors_bf.value,
            2400
        )
        self.assertEqual(
            debtors_bf.nominal,
            self.debtors_nominal
        )

        # 2
        self.assertEqual(
            vat_output_bf.module,
            "NL"
        )
        self.assertEqual(
            vat_output_bf.header,
            1
        )
        self.assertEqual(
            vat_output_bf.date,
            date.today()
        )
        self.assertEqual(
            vat_output_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            vat_output_bf.period,
            self.period_202001
        )
        self.assertEqual(
            vat_output_bf.type,
            "nbf"
        )
        self.assertEqual(
            vat_output_bf.field,
            "t"
        )
        self.assertEqual(
            vat_output_bf.value,
            -400
        )
        self.assertEqual(
            vat_output_bf.nominal,
            self.vat_output
        )

        # 3
        self.assertEqual(
            retained_earnings_bf.module,
            "NL"
        )
        self.assertEqual(
            retained_earnings_bf.header,
            1
        )
        self.assertEqual(
            retained_earnings_bf.date,
            date.today()
        )
        self.assertEqual(
            retained_earnings_bf.ref,
            f"YEAR END {str(self.fy_2019)}"
        )
        self.assertEqual(
            retained_earnings_bf.period,
            self.period_202001
        )
        self.assertEqual(
            retained_earnings_bf.type,
            "nbf"
        )
        self.assertEqual(
            retained_earnings_bf.field,
            "t"
        )
        self.assertEqual(
            retained_earnings_bf.value,
            -2000
        )
        self.assertEqual(
            retained_earnings_bf.nominal,
            self.retained_earnings
        )

        # 2020 trans -- second FY
        t1 = NominalTransaction.objects.create(
            module="SL",
            header=3,
            line=1,
            ref="1",
            period=self.period_202001,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t2 = NominalTransaction.objects.create(
            module="SL",
            header=3,
            line=2,
            ref="1",
            period=self.period_202001,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t3 = NominalTransaction.objects.create(
            module="SL",
            header=3,
            line=3,
            ref="1",
            period=self.period_202001,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )
        t4 = NominalTransaction.objects.create(
            module="SL",
            header=4,
            line=1,
            ref="2",
            period=self.period_202001,
            field="g",
            type="si",
            nominal=self.sales,
            value=-1000,
            date=date.today()
        )
        t5 = NominalTransaction.objects.create(
            module="SL",
            header=4,
            line=2,
            ref="2",
            period=self.period_202001,
            field="v",
            type="si",
            nominal=self.vat_output,
            value=-200,
            date=date.today()
        )
        t6 = NominalTransaction.objects.create(
            module="SL",
            header=4,
            line=3,
            ref="2",
            period=self.period_202001,
            field="t",
            type="si",
            nominal=self.debtors_nominal,
            value=1200,
            date=date.today()
        )

        NominalTransaction.objects.carry_forward(
            self.fy_2020, self.period_202101)
        nom_trans = NominalTransaction.objects.all().order_by("pk")
        self.assertEqual(
            len(nom_trans),
            18
        )
        # we had 9 before this year end so we only care about those after
        nom_trans = nom_trans[9:]
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )
        self.assertEqual(
            nom_trans[2],
            t3
        )
        self.assertEqual(
            nom_trans[3],
            t4
        )
        self.assertEqual(
            nom_trans[4],
            t5
        )
        self.assertEqual(
            nom_trans[5],
            t6
        )

        for bf in nom_trans[6:]:
            if bf.nominal == self.vat_output:
                vat_output_bf = bf
            elif bf.nominal == self.debtors_nominal:
                debtors_bf = bf
            elif bf.nominal == self.retained_earnings:
                retained_earnings_bf = bf

        lines = [vat_output_bf.line, debtors_bf.line,
                 retained_earnings_bf.line]
        lines.sort()

        self.assertEqual(
            [1, 2, 3],
            lines
        )

        # 1
        self.assertEqual(
            debtors_bf.module,
            "NL"
        )
        self.assertEqual(
            debtors_bf.header,
            2
        )
        self.assertEqual(
            debtors_bf.date,
            date.today()
        )
        self.assertEqual(
            debtors_bf.ref,
            f"YEAR END {str(self.fy_2020)}"
        )
        self.assertEqual(
            debtors_bf.period,
            self.period_202101
        )
        self.assertEqual(
            debtors_bf.type,
            "nbf"
        )
        self.assertEqual(
            debtors_bf.field,
            "t"
        )
        self.assertEqual(
            debtors_bf.value,
            4800
        )
        self.assertEqual(
            debtors_bf.nominal,
            self.debtors_nominal
        )

        # 2
        self.assertEqual(
            vat_output_bf.module,
            "NL"
        )
        self.assertEqual(
            vat_output_bf.header,
            2
        )
        self.assertEqual(
            vat_output_bf.date,
            date.today()
        )
        self.assertEqual(
            vat_output_bf.ref,
            f"YEAR END {str(self.fy_2020)}"
        )
        self.assertEqual(
            vat_output_bf.period,
            self.period_202101
        )
        self.assertEqual(
            vat_output_bf.type,
            "nbf"
        )
        self.assertEqual(
            vat_output_bf.field,
            "t"
        )
        self.assertEqual(
            vat_output_bf.value,
            -800
        )
        self.assertEqual(
            vat_output_bf.nominal,
            self.vat_output
        )

        # 3
        self.assertEqual(
            retained_earnings_bf.module,
            "NL"
        )
        self.assertEqual(
            retained_earnings_bf.header,
            2
        )
        self.assertEqual(
            retained_earnings_bf.date,
            date.today()
        )
        self.assertEqual(
            retained_earnings_bf.ref,
            f"YEAR END {str(self.fy_2020)}"
        )
        self.assertEqual(
            retained_earnings_bf.period,
            self.period_202101
        )
        self.assertEqual(
            retained_earnings_bf.type,
            "nbf"
        )
        self.assertEqual(
            retained_earnings_bf.field,
            "t"
        )
        self.assertEqual(
            retained_earnings_bf.value,
            -4000
        )
        self.assertEqual(
            retained_earnings_bf.nominal,
            self.retained_earnings
        )


class RollbackFYTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="dummy", password="dummy")
        cls.fy_2019 = fy = FinancialYear.objects.create(financial_year=2019)
        cls.period_201901 = Period.objects.create(
            fy=fy, period="01", fy_and_period="201901", month_end=date(2019, 1, 31))
        cls.fy_2020 = fy = FinancialYear.objects.create(financial_year=2020)
        cls.period_202001 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202001", month_end=date(2020, 1, 31))
        cls.fy_2021 = fy = FinancialYear.objects.create(financial_year=2021)
        cls.period_202101 = Period.objects.create(
            fy=fy, period="01", fy_and_period="202101", month_end=date(2021, 1, 31))

        # P/L
        cls.revenue_1 = revenue_1 = Nominal.objects.create(
            name="revenue", type="pl")
        cls.revenue_2 = revenue_2 = Nominal.objects.create(
            name="revenue", type="pl", parent=revenue_1)
        cls.sales = sales = Nominal.objects.create(
            name="sales", type="pl", parent=revenue_2)

        # EXPENSES
        cls.expenses_1 = expenses_1 = Nominal.objects.create(
            name="expenses", type="pl")
        cls.expenses_2 = expenses_2 = Nominal.objects.create(
            name="expenses", type="pl", parent=expenses_1)
        cls.staff = staff = Nominal.objects.create(
            name="staff", type="pl", parent=expenses_2)

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

        # EQUITY
        cls.equity_1 = equity_1 = Nominal.objects.create(
            name="Equity", type="b")
        cls.equity_2 = equity_2 = Nominal.objects.create(
            name="Equity", type="b", parent=equity_1)
        cls.retained_earnings = retained_earnings = Nominal.objects.create(
            name="Retained Earnings",
            type="b",
            parent=equity_2
        )

    def test(self):
        # create two lots of bfs
        # check that only the correct set is deleted
        t1 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=1,
            date=date.today(),
            ref=f"YEAR END {str(self.fy_2019)}",
            period=self.period_201901,
            type="nbf",
            field="t",
            value=-1000,
            nominal=self.retained_earnings
        )
        t2 = NominalTransaction.objects.create(
            module="NL",
            header=1,
            line=2,
            date=date.today(),
            ref=f"YEAR END {str(self.fy_2019)}",
            period=self.period_201901,
            type="nbf",
            field="t",
            value=1000,
            nominal=self.debtors_nominal
        )
        fy_2020_bfs = []
        fy_2020_bfs.append(
            NominalTransaction(
                module="NL",
                header=2,
                line=1,
                date=date.today(),
                ref=f"YEAR END {str(self.fy_2020)}",
                period=self.period_202001,
                type="nbf",
                field="t",
                value=-1000,
                nominal=self.retained_earnings
            )
        )
        fy_2020_bfs.append(
            NominalTransaction(
                module="NL",
                header=2,
                line=2,
                date=date.today(),
                ref=f"YEAR END {str(self.fy_2020)}",
                period=self.period_202001,
                type="nbf",
                field="t",
                value=1000,
                nominal=self.debtors_nominal
            )
        )
        NominalTransaction.objects.bulk_create(fy_2020_bfs)
        NominalTransaction.objects.rollback_fy(self.fy_2020)
        nom_trans = NominalTransaction.objects.all().order_by(*
                                                              ["header", "line"])
        self.assertEqual(
            len(nom_trans),
            2
        )
        self.assertEqual(
            nom_trans[0],
            t1
        )
        self.assertEqual(
            nom_trans[1],
            t2
        )

from datetime import date

from cashbook.models import CashBook
from controls.models import FinancialYear, ModuleSettings, Period, QueuePosts
from nominals.models import Nominal
from purchases.models import Supplier
from sales.models import Customer
from vat.models import Vat


def run():

    # A row should exist for each module from which you can post
    QueuePosts.objects.get_or_create(module="c")  # cashbook
    QueuePosts.objects.get_or_create(module="n")  # nominals
    QueuePosts.objects.get_or_create(module="p")  # purchases
    QueuePosts.objects.get_or_create(module="s")  # sales

    # revenue
    revenue = Nominal.objects.create(name="Revenue", type="pl")
    revenue = Nominal.objects.create(name="Revenue", type="pl", parent=revenue)
    # expenses
    expenses = Nominal.objects.create(name="Expenses", type="pl")
    expenses = Nominal.objects.create(
        name="Expenses", type="pl", parent=expenses)
    # assets
    assets = Nominal.objects.create(name="Assets", type="b")
    current_assets = Nominal.objects.create(
        name="Current Assets", parent=assets, type="b")
    Nominal.objects.create(name="Sales Ledger Control",
                           parent=current_assets, type="b")
    bank_account = Nominal.objects.create(
        name="Bank Account", parent=current_assets, type="b")
    Nominal.objects.create(name="Prepayments", parent=current_assets, type="b")
    non_current_assets = Nominal.objects.create(
        name="Non Current Assets", parent=assets, type="b")
    Nominal.objects.create(name="Land", parent=non_current_assets, type="b")
    # liabilities
    liabilities = Nominal.objects.create(name="Liabilities", type="b")
    current_liabilities = Nominal.objects.create(
        name="Current Liabilities", parent=liabilities, type="b")
    Nominal.objects.create(name="Purchase Ledger Control",
                           parent=current_liabilities, type="b")
    Nominal.objects.create(
        name="Vat Control", parent=current_liabilities, type="b")
    non_current_liabilities = Nominal.objects.create(
        name="Non Current Liabilities", parent=liabilities, type="b")
    Nominal.objects.create(
        name="Loans", parent=non_current_liabilities, type="b")
    # equity
    equity = Nominal.objects.create(name="Equity", type="b")
    equity = Nominal.objects.create(name="Equity", type="b", parent=equity)
    retained_earnings = Nominal.objects.create(
        name="Retained Earnings", parent=equity, type="b")
    # system controls
    system_controls = Nominal.objects.create(name="System Controls", type="b")
    system_suspenses = Nominal.objects.create(
        name="System Suspenses", parent=system_controls, type="b")
    default_system_suspense = Nominal.objects.create(
        name="System Suspense Account", parent=system_suspenses, type="b")

    CashBook.objects.create(name="Current", nominal=bank_account)

    vat_rates = [
        Vat(**{
            "code": "1",
            "name": "Standard Rate",
            "rate": 20,
            "registered": True
        }),
        Vat(**{
            "code": "2",
            "name": "Reduced Rate",
            "rate": 5,
            "registered": True
        })
    ]
    Vat.objects.bulk_create(vat_rates)

    fy = FinancialYear.objects.create(
        financial_year=2021, number_of_periods=12)
    periods = []
    for i in range(1, 13):
        p = str(i).rjust(2, "0")
        p = Period(period=p, fy_and_period="2021" + p,
                   month_start=date(2021, i, 1), fy=fy)
        periods.append(p)
    Period.objects.bulk_create(periods)

    first_period = Period.objects.first()

    ModuleSettings.objects.create(cash_book_period=first_period, nominals_period=first_period,
                                  purchases_period=first_period, sales_period=first_period)
    # there should only ever be one record
    Customer.objects.create(name="Hilton", code="hilton", customer=True)
    Supplier.objects.create(name="Screwfix", code="screw", supplier=True)
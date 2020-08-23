from .models import Nominal

def create_nominals():
    assets = Nominal.objects.create(name="Assets")
    current_assets = Nominal.objects.create(name="Current Assets", parent=assets)
    Nominal.objects.create(name="Bank Account", parent=current_assets)
    Nominal.objects.create(name="Prepayments", parent=current_assets)
    non_current_assets = Nominal.objects.create(name="Non Current Assets", parent=assets)
    Nominal.objects.create(name="Land", parent=non_current_assets)
    liabilities = Nominal.objects.create(name="Liabilities")
    current_liabilities = Nominal.objects.create(name="Current Liabilities", parent=liabilities)
    Nominal.objects.create(name="Purchase Ledger Control", parent=current_liabilities)
    Nominal.objects.create(name="Vat Control", parent=current_liabilities)
    non_current_liabilities = Nominal.objects.create(name="Non Current Liabilities", parent=liabilities)
    Nominal.objects.create(name="Loans", parent=non_current_liabilities)
    system_controls = Nominal.objects.create(name="System Controls")
    opening_balances = Nominal.objects.create(name="Opening Balances", parent=system_controls)
    system_suspenses = Nominal.objects.create(name="System Suspenses", parent=system_controls)
    default_system_suspense = Nominal.objects.create(name="System Suspense Account", parent=system_suspenses)



def create_default_data():
    create_nominals()
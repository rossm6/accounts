from cashbook.models import CashBook
from contacts.models import Contact
from django.apps import apps
from django.contrib.auth import get_user_model
from nominals.helpers import create_default_data as nl_create_default_data
from nominals.models import Nominal
from purchases.helpers import create_default_data as pl_create_default_data
from sales.helpers import create_default_data as sl_create_default_data
from vat.helpers import create_default_data as vt_create_default_data

apps_db_data = [
    'cashbook',
    'nominals',
    'purchases',
    'sales',
    'vat'
]

def init():
    """
    Delete everything and then create default data

    If you want full audit history for the default data remember to run this utility cmd -

        python3 manage.py populate_history --auto

    """

    for app in apps_db_data:
        for model in apps.get_app_config(app).get_models():
            model.objects.all().delete()
            if hasattr(model, "history"):
                model.history.all().delete()

    Contact.history.all().delete() # because history does not exist on the Supplier and Customer proxy models

    get_user_model().objects.all().delete()
    get_user_model().objects.create_user(username="ross", password="Test123!", is_superuser=True, is_staff=True)
    
    nl_create_default_data() # does not bulk_create so will create audits too
    pl_create_default_data()
    sl_create_default_data()
    vt_create_default_data()

    bank_nominal = Nominal.objects.get(name="Bank Account")
    CashBook.objects.create(
        name="Current",
        nominal=bank_nominal
    ) # will create audit record

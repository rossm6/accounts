from django.apps import apps
from django.contrib.auth import get_user_model

from cashbook.models import CashBook
from items.helpers import create_default_data as it_create_default_data
from nominals.models import Nominal
from nominals.helpers import create_default_data as nl_create_default_data
from purchases.helpers import create_default_data as pl_create_default_data
from vat.helpers import create_default_data as vt_create_default_data
from sales.helpers import create_default_data as sl_create_default_data

apps_db_data = [
    'cashbook',
    'items',
    'nominals',
    'purchases',
    'sales',
    'vat'
]

def init():
    """
    Delete everything and then create default data
    """

    for app in apps_db_data:
        for model in apps.get_app_config(app).get_models():
            model.objects.all().delete()


    get_user_model().objects.all().delete()
    get_user_model().objects.create_user(username="ross", password="Test123!", is_superuser=True, is_staff=True)
    
    it_create_default_data()
    nl_create_default_data()
    pl_create_default_data()
    sl_create_default_data()
    vt_create_default_data()

    bank_nominal = Nominal.objects.get(name="Bank Account")
    CashBook.objects.create(
        name="Current",
        nominal=bank_nominal
    )
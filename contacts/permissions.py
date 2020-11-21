from accountancy.helpers import BaseModelPermissions
from purchases.models import Supplier
from sales.models import Customer


class ContactsPermissions(BaseModelPermissions):
    module = "Contact"
    prefix = "contact"
    models = [
        {
            "model": Customer,
            "for_concrete_model": False,
            "section": "Maintenance"
        },
        {
            "model": Supplier,
            "for_concrete_model": False,
            "section": "Maintenance"
        },
    ]

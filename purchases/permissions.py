from accountancy.helpers import BaseModelPermissions

from purchases.models import PurchaseHeader


class PurchasesPermissions(BaseModelPermissions):
    module = "Purchases"
    prefix = "purchases"
    models = [
        {
            "model": PurchaseHeader,
            "exclude": [
                "add_purchaseheader",
                "change_purchaseheader",
                "delete_purchaseheader",
                "view_purchaseheader"
            ]
        },
    ]

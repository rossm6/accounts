from accountancy.helpers import BaseModelPermissions

from vat.models import Vat, VatTransaction


class VatPermissions(BaseModelPermissions):
    module = "Vat"
    prefix = "vat"
    models = [
        {
            "model": Vat,
            "section": "Maintenance"
        },
        {
            "model": VatTransaction,
            "exclude": [
                "add_vattransaction",
                "change_vattransaction",
                "delete_vattransaction",
                "view_vattransaction"
            ]
        },
    ]

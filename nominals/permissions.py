from accountancy.helpers import BaseModelPermissions

from nominals.models import Nominal, NominalHeader


class NominalsPermissions(BaseModelPermissions):
    module = "Nominal"
    prefix = "nominal"
    models = [
        {
            "model": Nominal,
            "section": "Maintenance"
        },
        {
            "model": NominalHeader,
            "exclude": [
                "add_nominalheader",
                "change_nominalheader",
                "delete_nominalheader",
                "view_nominalheader"
            ]
        },
    ]

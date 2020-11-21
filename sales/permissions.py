from accountancy.helpers import BaseModelPermissions

from sales.models import SaleHeader


class SalesPermissions(BaseModelPermissions):
    module = "Sales"
    prefix = "sales"
    models = [
        {
            "model": SaleHeader,
            "exclude": [
                "add_saleheader",
                "change_saleheader",
                "delete_saleheader",
                "view_saleheader"
            ]
        },
    ]

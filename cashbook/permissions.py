from accountancy.helpers import BaseModelPermissions

from cashbook.models import CashBook, CashBookHeader


class CashBookPermissions(BaseModelPermissions):
    module = "Cashbook"
    prefix = "cashbook"
    models = [
        {
            "model": CashBook,
            "section": "Maintenance"
        },
        {
            "model": CashBookHeader,
            "exclude": [
                "add_cashbookheader",
                "change_cashbookheader",
                "delete_cashbookheader",
                "view_cashbookheader"
            ]
        },
    ]

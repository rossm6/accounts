from vat.models import Vat

def create_default_data():
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
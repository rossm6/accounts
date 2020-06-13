from datetime import timedelta

from django.utils import timezone

from .models import Supplier, Invoice

def create_suppliers(n):
    suppliers = []
    i = 0
    with open('/etc/dictionaries-common/words', 'r') as dictionary:
        for word in dictionary:
            suppliers.append(
                Supplier(name=word)
            )
            if i > n:
                break
            i = i + 1
    return Supplier.objects.bulk_create(suppliers)


def create_invoices(supplier, ref_prefix, n):
    date = timezone.now()
    due_date = date + timedelta(days=31)
    invoices = []
    for i in range(n):
        i = Invoice(
            supplier=supplier,
            ref=ref_prefix + str(i),
            goods=100,
            discount=0,
            vat=20,
            total=120,
            paid=0,
            due=120,
            date=date,
            due_date=due_date,
            type="i"
        )
        invoices.append(i)
    return Invoice.objects.bulk_create(invoices)
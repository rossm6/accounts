from datetime import timedelta

from django.utils import timezone

from .models import Invoice, Payment, PurchaseHeader, PurchaseLine, Supplier

PERIOD = '202007'

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


def create_lines(header, lines):
    tmp = []
    for i, line in enumerate(lines):
        line["line_no"] = i + 1
        line["header"] = header
        tmp.append(PurchaseLine(**line))
    return PurchaseLine.objects.bulk_create(tmp)
    

def create_invoices(supplier, ref_prefix, n, value=100):
    date = timezone.now()
    due_date = date + timedelta(days=31)
    invoices = []
    for i in range(n):
        i = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            goods=value,
            vat=0.2 * value,
            total=1.2 * value,
            paid=0,
            due=1.2 * value,
            date=date,
            due_date=due_date,
            type="pi",
            period=PERIOD 
        )
        invoices.append(i)
    return PurchaseHeader.objects.bulk_create(invoices)


def create_payments(supplier, ref_prefix, n, value=100):
    date = timezone.now()
    due_date = date + timedelta(days=31)
    payments = []
    for i in range(n):
        p = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            total= -1 * value,
            paid=0,
            due= -1 * value,
            date=date,
            type="pp",
            period=PERIOD
        )
        payments.append(p)
    return PurchaseHeader.objects.bulk_create(payments)

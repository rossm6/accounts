from django.db import models

from accountancy.models import (Contact, MatchedHeaders, TransactionHeader,
                                TransactionLine)
from items.models import Item
from nominals.models import Nominal
from vat.models import Vat

class Supplier(Contact):
    pass

class PurchaseHeader(TransactionHeader):
    type_non_payments = [
        ('bi', 'Brought Forward Invoice'),
        ('bc', 'Brought Forward Credit Note'),
        ('i', 'Invoice'),
        ('c', 'Credit Note'),
    ]
    type_payments = [
        ('bp', 'Brought Forward Payment'),
        ('br', 'Brought Forward Refund'),
        ('p', 'Payment'),
        ('r', 'Refund'),
    ]
    type_choices = type_non_payments + type_payments
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=2,
        choices=type_choices
    )
    matched_to = models.ManyToManyField('self', through='PurchaseMatching', symmetrical=False)


class PurchaseLine(TransactionLine):
    header = models.ForeignKey(PurchaseHeader, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")

    class Meta:
        ordering = ['line_no']

class Payment(PurchaseHeader):
    class Meta:
        proxy = True

class Invoice(PurchaseHeader):
    class Meta:
        proxy = True

class CreditNote(PurchaseHeader):
    class Meta:
        proxy = True

class Refund(PurchaseHeader):
    class Meta:
        proxy = True


class PurchaseMatching(MatchedHeaders):
    # matched_by is the header record through which
    # all the other transactions were matched
    matched_by = models.ForeignKey(
        PurchaseHeader, 
        on_delete=models.CASCADE, 
        related_name="matched_by_these",
    )
    # matched_to is a header record belonging to
    # the set 'all the other transactions' described above
    matched_to = models.ForeignKey(
        PurchaseHeader, 
        on_delete=models.CASCADE, 
        related_name="matched_to_these"
    )

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

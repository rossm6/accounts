from django.db import models

from accountancy.models import (Contact, MatchedHeaders, TransactionHeader,
                                TransactionLine)
from items.models import Item
from vat.models import Vat

class Supplier(Contact):
    pass

class PurchaseHeader(TransactionHeader):
    no_analysis_required = [
        ('pbi', 'Brought Forward Invoice'),
        ('pbc', 'Brought Forward Credit Note'),
        ('pbp', 'Brought Forward Payment'),
        ('pbr', 'Brought Forward Refund'),
        ('pp', 'Payment'),
        ('pr', 'Refund'),
    ]
    analysis_required = [
        ('pi', 'Invoice'),
        ('pc', 'Credit Note'),
    ]
    no_lines_required = [
        ('pbp', 'Brought Forward Payment'),
        ('pbr', 'Brought Forward Refund'),
        ('pp', 'Payment'),
        ('pr', 'Refund'),
    ]
    lines_required = [
        ('pbi', 'Brought Forward Invoice'),
        ('pbc', 'Brought Forward Credit Note'),
        ('pi', 'Invoice'),
        ('pc', 'Credit Note'),
    ]
    credits = [
        'pbc',
        'pbp',
        'pp',
        'pc'
    ]
    debits = [
        'pbi',
        'pbr',
        'pr',
        'pi'
    ]
    payment_type = [
        'pbp',
        'pbr',
        'pp',
        'pr'
    ]
    # TO DO - issue an improperly configured warning if all the types are not all the
    # credit types plus the debit types
    type_choices = no_analysis_required + analysis_required
    cash_book = models.ForeignKey('cashbook.CashBook', on_delete=models.CASCADE, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=3,
        choices=type_choices
    )
    matched_to = models.ManyToManyField('self', through='PurchaseMatching', symmetrical=False)



class PurchaseLineQuerySet(models.QuerySet):

    def line_bulk_update(self, instances):
        return self.bulk_update(
            instances,
            [
                "line_no",
                "description",
                "goods",
                "vat",
                "item",
                "nominal",
                "vat_code"
            ]
        )


class PurchaseLine(TransactionLine):
    header = models.ForeignKey(PurchaseHeader, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True, blank=True)
    nominal = models.ForeignKey('nominals.Nominal', on_delete=models.CASCADE, null=True, blank=True)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vat Code")
    goods_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="purchase_good_line")
    vat_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="purchase_vat_line")
    total_nominal_transaction = models.ForeignKey('nominals.NominalTransaction', null=True, blank=True, on_delete=models.CASCADE, related_name="purchase_total_line")

    # It does not make sense that a line would exist without a nominal transaction but the purchase line is created
    # before the nominal transaction so it must do the create without the id for the nominal transaction

    objects = PurchaseLineQuerySet.as_manager()

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
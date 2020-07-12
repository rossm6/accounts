from decimal import Decimal

from django.db import models

from items.models import Item
from nominals.models import Nominal
from vat.models import Vat


class Contact(models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True




class DecimalBaseModel(models.Model):

    """
    The purpose of this class is simply to make sure the decimal zero is
    saved instead of null to the database.  At first i had 0.00 as the
    default value set against each field on the model but i don't like
    this showing as the initial value in the creation form.

    REMEMBER - clean is called as part of the full_clean process which
    itself it not called during save()
    """

    pass

    class Meta:
        abstract = True

    def clean(self):
        fields = self._meta.get_fields()
        for field in fields:
            if field.__class__ is models.fields.DecimalField:
                field_name = field.name
                field_value = getattr(self, field_name)
                if field_value == None:
                    setattr(self, field_name, Decimal(0.00))


class TransactionHeader(DecimalBaseModel):
    """
    Base transaction which can be sub classed.
    Subclasses will likely need to include a
    type property.  And a proxy model for each
    type which is a proxy of this transaction
    class.

    Examples below for sales ledger
    """
    ref = models.CharField(max_length=20)
    goods = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    discount = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True   
    )
    total = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    paid = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    due = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True) # payments do not require due dates
    # type = models.CharField(
    #     max_length=1,
    #     choices=[
    #         ('r', 'receipt'),
    #         ('i', 'invoice')
    #     ]
    # )
    # matched_to = models.ManyToManyField('self', through='Matching')

    class Meta:
        abstract = True


# class Invoice(TransactionHeader):
#     class Meta:
#         proxy = True



# class Receipt(TransactionHeader):
#     class Meta:
#         proxy = True


class TransactionLine(DecimalBaseModel):
    line_no = models.IntegerField()
    description = models.CharField(max_length=100)
    goods = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )
    vat = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True
    )

    class Meta:
        abstract = True


class MatchedHeaders(models.Model):
    """
    Subclass must add the transaction_1 and transaction_2 foreign keys
    """
    # transaction_1 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="first_transaction")
    # transaction_2 = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="second_transaction")
    created = models.DateField(auto_now_add=True)
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )

    class Meta:
        abstract = True



"""

The following models are used for testing.

Except this would mean copying all the views too.  I can't see the point of this.  Just keep the purchase app we have but rename the
app so that it is "dummy_purchases" or something and use this for continuous integration.

"""

class TestSupplier(Contact):
    pass

class TestPurchaseHeader(TransactionHeader):
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
    supplier = models.ForeignKey(TestSupplier, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=2,
        choices=type_choices
    )
    matched_to = models.ManyToManyField('self', through='TestPurchaseMatching', symmetrical=False)


class TestPurchaseLine(TransactionLine):
    header = models.ForeignKey(TestPurchaseHeader, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    nominal = models.ForeignKey(Nominal, on_delete=models.CASCADE)
    vat_code = models.ForeignKey(Vat, on_delete=models.SET_NULL, null=True, verbose_name="Vat Code")

class TestPayment(TestPurchaseHeader):
    class Meta:
        proxy = True

class TestInvoice(TestPurchaseHeader):
    class Meta:
        proxy = True

class TestCreditNote(TestPurchaseHeader):
    class Meta:
        proxy = True

class TestRefund(TestPurchaseHeader):
    class Meta:
        proxy = True


class TestPurchaseMatching(MatchedHeaders):
    # matched_by is the header record through which
    # all the other transactions were matched
    matched_by = models.ForeignKey(
        TestPurchaseHeader, 
        on_delete=models.CASCADE, 
        related_name="matched_by_these",
    )
    # matched_to is a header record belonging to
    # the set 'all the other transactions' described above
    matched_to = models.ForeignKey(
        TestPurchaseHeader, 
        on_delete=models.CASCADE, 
        related_name="matched_to_these"
    )

    # So we can do for two trans, t1 and t2
    # t1.matched_to_these.all()
    # t2.matched_by_these.all()

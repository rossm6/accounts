from django.db import models


class Contact(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True

class TransactionHeader(models.Model):
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
        default=0    
    )
    discount = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0   
    )
    vat = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0     
    )
    total = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )
    paid = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )
    due = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        default=0
    )
    date = models.DateField()
    due_date = models.DateField()
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


class TransactionLine(models.Model):
    line_no = models.IntegerField()
    description = models.CharField(max_length=100)
    amount = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        blank=True,
        null=True,
        default=None
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
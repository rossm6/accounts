from decimal import Decimal

from django.db import models


class Contact(models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.code

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
    statuses = [
        ("c", "cleared"),
        ("v", "void"),
    ]
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
    period = models.CharField(max_length=6) # example 202001, 202002.  This way we can sort easily.
    status = models.CharField(max_length=2, choices=statuses, default="c")

    class Meta:
        abstract = True

    @classmethod
    def get_types_requiring_analysis(cls):
        return [ type[0] for type in cls.analysis_required ]

    @classmethod
    def get_type_names_requiring_analysis(cls):
        return [ type[1] for type in cls.analysis_required ]

    @classmethod
    def get_types_requiring_lines(cls):
        return [ type[0] for type in cls.lines_required ]

    @classmethod
    def get_type_names_requiring_lines(cls):
        return [ type[1] for type in cls.lines_required ]


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

    def add_nominal_transactions(self, nominal_trans):
        if "g" in nominal_trans:
            self.goods_nominal_transaction = nominal_trans["g"]
        if "v" in nominal_trans:
            self.vat_nominal_transaction = nominal_trans["v"]


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
    period = models.CharField(max_length=6) # example 202001, 202002.  This way we can sort easily.

    class Meta:
        abstract = True
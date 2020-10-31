from decimal import Decimal


class DecimalDescriptor:
    """
    Decimal fields on models will generally want to allow a
    null value.

    So that a decimal value is shown when the model is shown
    we need to convert if it not a decimal already.

    The problem with setting a decimal, or any number, as the
    default is it will show as the default in form fields which
    doesn't look great.
    """
    TWO_PLACES = Decimal(10) ** -2

    def __init__(self, name):
        self.name = name

    def __get__(self, instance=None, owner=None):
        value = instance.__dict__.get(self.name)
        if not value:
            value = Decimal(0)
        return value.quantize(self.TWO_PLACES)

    def __set__(self, instance, value):
        positve_zero = Decimal(0.00).quantize(self.TWO_PLACES)
        if isinstance(value, (float, int)):
            value = Decimal(value)
        if isinstance(value, Decimal):
            value = value.quantize(self.TWO_PLACES)
        if value == positve_zero:
            # avoid negative 0
            value = positve_zero
        instance.__dict__[self.name] = value


class UIDecimalDescriptor(DecimalDescriptor):
    """
    A total of the credit note will show in the DB as a
    negative value but in the UI will need to show as a positive.

    This descriptor encapsulates this logic.
    """
    def __get__(self, instance=None, owner=None):
        value = super().__get__(instance=instance, owner=owner)
        if instance.is_negative_type():
            value *= -1
        if not value:
            value = Decimal(0.00).quantize(self.TWO_PLACES)
        return value

    def __set__(self, instance, value):
        super().__set__(instance, value)
        value = instance.__dict__[self.name]
        if value is not None:
            if instance.is_negative_type() and value != Decimal(0):
                instance.__dict__[self.name] = value * -1

from decimal import Decimal


class DecimalDescriptor:
    """
    Decimal fields on models will generally want allow a
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
        if not value:  # take care of -0
            value = Decimal(0)
        return value.quantize(self.TWO_PLACES)

    def __set__(self, instance, value):
        if isinstance(value, (float, int)):
            value = Decimal(value)
        if isinstance(value, Decimal):
            value = value.quantize(self.TWO_PLACES)
        instance.__dict__[self.name] = value


class UIDecimalDescriptor(DecimalDescriptor):

    def __get__(self, instance=None, owner=None):
        value = super().__get__(instance=instance, owner=owner)
        if instance.is_negative_type():
            value *= -1
        return value

    def __set__(self, instance, value):
        if instance.is_negative_type():
            value *= -1
        super().__set__(instance, value)

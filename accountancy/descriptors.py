from decimal import Decimal

"""
DRY violated here
"""

class UIDecimalDescriptor:
    TWO_PLACES = Decimal(10) ** -2
    def __init__(self, name):
        self.name = name

    def __get__(self, instance=None, owner=None):
        value = instance.__dict__[self.name]
        if not value:  # True if value is -0.00
            return Decimal(0.00)
        if instance.is_negative_type():
            return -1 * value
        return value.quantize(self.TWO_PLACES)

    def __set__(self, instance, value):
        if isinstance(value, (float, int)):
            value = Decimal(value)
        if instance.is_negative_type():
            value = -1 * value
        instance.__dict__[self.name] = value.quantize(self.TWO_PLACES)


class DecimalDescriptor:
    TWO_PLACES = Decimal(10) ** -2

    def __init__(self, name):
        self.name = name
        TWO_PLACES = Decimal(10) ** -2

    def __get__(self, instance=None, owner=None):
        value = instance.__dict__[self.name]
        if not value:  # take care of -0
            value = Decimal(0)
        return value.quantize(self.TWO_PLACES)

    def __set__(self, instance, value):
        if isinstance(value, (float, int)):
            value = Decimal(value)
        instance.__dict__[self.name] = value

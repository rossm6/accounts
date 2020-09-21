from datetime import date, timedelta
from functools import reduce

from django.urls import reverse_lazy
from django.utils import timezone


class JSONBlankDate(date):
    """
    The serializer used by Django when encoding into Json for JsonResponse
    is `DjangoJSONEncoder`

    Per - https://docs.djangoproject.com/en/3.1/topics/serialization/

    And this serializer uses the isoformat method on the date object
    for getting the value for the json.  Per - https://github.com/django/django/blob/master/django/core/serializers/json.py

    This subclass just returns an empty string for the json response.  It is used with the creditor and debtor reports.
    A date object is needed to sort the objects based on this but the database value is ''.
    """

    def isoformat(self):
        return ""


class FY:
    """
    Financial Year class.
    """
    def __init__(self, period_str, periods_in_fy=12):
        if len(period_str) != 6:
            raise ValueError(
                "The period must be 6 characters.  "
                "The first 4 is the FY and the last two is the accounting period."
            )
        self.period = period_str

    def start(self):
        fy, period = int(self.period[:4]), int(self.period[4:])
        return str(fy) + "01" 
    
class Period:
    def __init__(self, period_str, periods_in_fy=12):
        if len(period_str) != 6:
            raise ValueError(
                "The period must be 6 characters.  "
                "The first 4 is the FY and the last two is the accounting period."
            )
        self.period = period_str
        self.periods_in_fy = periods_in_fy

    def __sub__(self, other):
        # necessarily a period str must be 6 chars
        # first 4 is the FY e.g. 2020
        # last 2 is the period in the FY e.g 07
        fy, period = int(self.period[:4]), int(self.period[4:])
        years_subtracted = (period - 1 - other) // self.periods_in_fy
        fy = str(fy + years_subtracted)
        period = ((period - 1 - other) % self.periods_in_fy) + 1
        period = f'{period:02}'
        return fy + period

    def __add__(self, other):
        # necessarily a period str must be 6 chars
        # first 4 is the FY e.g. 2020
        # last 2 is the period in the FY e.g 07
        fy, period = int(self.period[:4]), int(self.period[4:])
        years_advanced = (period - 1 + other) // self.periods_in_fy
        fy = str(fy + years_advanced)
        period = ((period - 1 + other) % self.periods_in_fy) + 1
        period = f'{period:02}'
        return fy + period

    def __eq__(self, other):
        if type(other) is type(self):
            return str(self) == str(other)
        else:
            return str(self) == other

    def __le__(self, other):
        if type(other) is type(self):
            return str(self) <= str(other)
        else:
            return str(self) <= other

    # NOT TESTED
    def __lt__(self, other):
        if type(other) is type(self):
            return str(self) < str(other)
        else:
            return str(self) < other

    # NOT TESTED
    def __ge__(self, other):
        if type(other) is type(self):
            return str(self) >= str(other)
        else:
            return str(self) >= other

    # NOT TESTED
    def __gt__(self, other):
        if type(other) is type(self):
            return str(self) > str(other)
        else:
            return str(self) > other

    def __str__(self):
        return self.period


def delay_reverse_lazy(viewname, query_params=""):
    def _delay_reverse_lazy():
        return reverse_lazy(viewname) + ("?" + query_params if query_params else "")
    return _delay_reverse_lazy


def get_index_of_object_in_queryset(queryset, obj, key):
    try:
        for i, o in enumerate(queryset):
            if getattr(o, key) == getattr(obj, key):
                return i
    except:
        pass


def input_dropdown_widget_attrs_config(app_name, fields):
    configs = {}
    for field in fields:
        configs[field] = {
            "data-new": "#new-" + field,
            "data-load-url": delay_reverse_lazy(app_name + ":load_options", "field=" + field),
            "data-validation-url": delay_reverse_lazy(app_name + ":validate_choice", "field=" + field)
        }
    return configs


def sort_multiple(sequence, *sort_order):
    """Sort a sequence by multiple criteria.

    Accepts a sequence and 0 or more (key, reverse) tuples, where
    the key is a callable used to extract the value to sort on
    from the input sequence, and reverse is a boolean dictating if
    this value is sorted in ascending or descending order.

    This can be difficult to understand on first reading.  So here
    it is step by step -

    First the definition of reduce per the manual -
        reduce(function, sequence[, initial])
        If the optional initial parameter is passed it is placed
        before the items of the sequence in the calculation, and
        serves as a default when the sequence is empty.

    The sequence here is passed so the initial is the first
    item passed to the function.

    In the first instance the function is therefore passed
    the initial sequence - 3rd parameter - and the first
    element of the reversed sequence - the 2nd parameter.
    So the s parameter is the initial sequence and the order parameter
    is the first element of the reversed sequence.

    The output of the function - the initial sequence sorted based
    on the first order condition - then becomes the s parameter
    for the second function call and the next order is taken.
    So on and so forth until the ordering has been exhausted.

    Remember that sorted() returns a new list.

    e.g.

    auctions = Auction.objects.all()
    sort_multiple(auctions, *[(lambda a : a.finish, True)])

    This sorts the auctions in descending finish order.

    """

    return reduce(
        lambda s, order: sorted(s, key=order[0], reverse=order[1]),
        reversed(sort_order),
        sequence
    )

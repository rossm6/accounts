from functools import partial
from itertools import groupby
from operator import attrgetter

from django.forms import ModelChoiceField
from django.forms.models import ModelChoiceField, ModelChoiceIterator

from .widgets import InputDropDown

# Not in use at the moment but a start if you choose to later try and create your own custom form field class
# which uses the InputDropDown widget as the default.  The problem I had was working out how to pass widget attrs
# and to set them on the class.  I guess I could just have passed a widget instance with the attrs already set
# in between the super constructor call ...

class GroupedModelChoiceIterator(ModelChoiceIterator):
    # source - https://simpleisbetterthancomplex.com/tutorial/2019/01/02/how-to-implement-grouped-model-choice-field.html
    """
    This is good enough for our account grouping, for example, if we
    only have two levels i.e. a header and a subcode.

    It's no good though if we have more levels.  See below for
    the solution to this.
    """
    def __init__(self, field, groupby):
        self.groupby = groupby
        super().__init__(field)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
            # yield returns ("", self.field.empty_label)
            # but the difference is the next time we call next()
            # on the GroupModelChoiceIterator
            # execution starts from the next line
            # i.e. queryset = self.queryset
        queryset = self.queryset
        # Can't use iterator() when queryset uses prefetch_related()
        if not queryset._prefetch_related_lookups:
            queryset = queryset.iterator()
            # need to do this because groupby expects an iterable
        for group, objs in groupby(queryset, self.groupby):
            yield (group, [self.choice(obj) for obj in objs])



class GroupedModelChoiceField(ModelChoiceField):
    """
    
    Like the GroupModelChoiceIterator this was sourced from -
    https://simpleisbetterthancomplex.com/tutorial/2019/01/02/how-to-implement-grouped-model-choice-field.html

    It was used to create the RootAndLeavesModelChoiceIterator.
    """

    def __init__(self, *args, choices_groupby, **kwargs):
        if isinstance(choices_groupby, str):
            choices_groupby = attrgetter(choices_groupby)
            # e.g.
            # if, choices_groupby = attrgetter('parent')
            # then, choices_groupby(obj) will return obj.parent
        elif not callable(choices_groupby):
            raise TypeError('choices_groupby must either be a str or a callable accepting a single argument')
        self.iterator = partial(GroupedModelChoiceIterator, groupby=choices_groupby)
        # partial returns the an object which can be called
        # this will call the first argument function passed to partial - here 'GroupedModelChoiceIterator'
        # so -
        # ModelChoiceField will set the choices attribute on the widget object
        # by calling self.iterator with the field as the first argument
        # which is same as -
        # widget.choices = self.iterator(field)
        # widget.choices = GroupModelChoiceIterator(field, choices_groupby)
        super().__init__(*args, **kwargs)
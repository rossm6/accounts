from functools import partial
from itertools import groupby
from operator import attrgetter

from django.forms.models import ModelChoiceField, ModelChoiceIterator

class RootAndLeavesModelChoiceIterator(ModelChoiceIterator):
    """
    Based on the Xero accounts software we wish to show a
    list of account nominals where an account structure like -

        Assets
            Current Assets
                Bank Account

    Would show as

        Assets
            Bank Account

    In order words, get all the roots in the nominal tree
    structure, and get all the leaves for each root.

    Only there is a problem if the queryset provided is
    paginated because the group may not be included
    in the queryset.  We therefore program defensively
    to take this possibility into account.

    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        tree = self.queryset # must be Model.objects.all().prefetch_related('children')
        leaves = []
        root_and_leaves = (None, leaves)
        for node in tree:
            if node.is_root_node():
                if leaves:
                    yield root_and_leaves
                    leaves = []
                root_and_leaves = (node.name, leaves)
            elif node.is_leaf_node():
                leaves.append(self.choice(node))
        yield root_and_leaves


#    PRETTY SURE THIS IS WRONG SO NEEDS CORRECTING, ALTHOUGH WE DON'T SEEM TO DO len(self.choices)
#    def __len__(self):
#         # count() adds a query but uses less memory since the QuerySet results
#         # won't be cached. In most cases, the choices will only be iterated on,
#         # and __len__() won't be called.
#         return self.queryset.count() + (1 if self.field.empty_label is not None else 0)




class ModelChoiceIteratorWithFields(ModelChoiceIterator):

    """

        ModelChoiceIterator gives us the value - usually the primary key of the object -
        and the label.  But when the user chooses a vat code object we also need to know
        the Vat rate, which is an attribute of the model.

        This is iterator will us -

            (value, label, [ (object_attr, object_attr_value), (object_attr, object_attr_value) ])

        It is envisaged the widget will have a lookup field attribute dictionary for picking
        which of these it needs and then add them as data attributes to the option html.
        If we already have a value we also need to add the data attributes.

        So the widget code -

            for value, label, *model_attrs in self.choices:
                # do stuff
                if *model_attrs:
                    pass

    """

    def choice(self, obj):
        c = super().choice(obj) # ('< class ModelChoiceIteratorValue>', 'some_label')
        value = c[0]
        label = c[1]
        fields = obj._meta.get_fields()
        tmp = []
        for field in fields:
            try:
                attr = field.name
                attr_value = getattr(obj, attr)
                tmp.append(
                    (attr, attr_value)
                )
            except:
                pass
        return (value, label, tmp)



class AjaxModelChoiceField(ModelChoiceField):
    def __init__(self, *args, **kwargs):
        queryset = kwargs["get_queryset"]
        querysets = {}
        querysets["get_queryset"] = kwargs.pop("get_queryset")
        querysets["load_queryset"] = kwargs.pop("load_queryset")
        querysets["post_queryset"] = kwargs.pop("post_queryset")
        querysets["inst_queryset"] = kwargs.pop("inst_queryset")
        if iterator := kwargs.get("iterator"):
            kwargs.pop("iterator")
        searchable_fields = kwargs.pop("searchable_fields")
        super().__init__(queryset, *args, **kwargs)
        for queryset in querysets:
            setattr(self, queryset, querysets[queryset])
        self.searchable_fields = searchable_fields
        if iterator:
            self.iterator = iterator


# FIX ME - remove this class and add the iterator manually to AjaxRoortAndLeavesModelChoiceField
class RootAndLeavesModelChoiceField(object):

    def __init__(self, *args, **kwargs):
        self.iterator = RootAndLeavesModelChoiceIterator


class AjaxRootAndLeavesModelChoiceField(AjaxModelChoiceField, RootAndLeavesModelChoiceField):
    pass
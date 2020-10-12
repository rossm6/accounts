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
        tree = self.queryset  # must be Model.objects.all().prefetch_related('children')
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

    def __len__(self):
        length = 0
        tree = self.queryset
        for node in tree:
            if node.is_root_node() or node.is_leaf_node():
                length = length + 1
        return length + (1 if self.field.empty_label is not None else 0)


class RootAndChildrenModelChoiceIterator(ModelChoiceIterator):
    """

    When creating nominal codes one needs to pick the account type i.e.
    the child of a root.

    This structure is built into the software.  Might make the whole thing
    user definable later on.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        tree = self.queryset  # must be Model.objects.all().prefetch_related('children')
        children = []
        root_and_children = (None, children)
        for node in tree:
            if node.is_root_node():
                if children:
                    yield root_and_children
                    children = []
                root_and_children = (node.name, children)
            elif node.is_child_node() and not node.is_leaf_node():
                children.append(self.choice(node))
        yield root_and_children

    def __len__(self):
        length = 0
        tree = self.queryset
        for node in tree:
            if node.is_root_node() or (node.is_child_node() and not node.is_leaf_node()):
                length = length + 1
        return length + (1 if self.field.empty_label is not None else 0)


class ModelChoiceIteratorWithFields(ModelChoiceIterator):

    """

        ModelChoiceIterator gives us the value - usually the primary key of the object -
        and the label.  But when the user chooses a vat code object we also need to know
        the Vat rate, which is an attribute of the model.

        This iterator will give us -

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
        c = super().choice(obj)  # ('< class ModelChoiceIteratorValue>', 'some_label')
        value, label = c
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

class ModelChoiceFieldChooseIterator(ModelChoiceField):
    def __init__(self, *args, **kwargs):
        iterator = kwargs.pop("iterator")
        super().__init__(*args, **kwargs)
        self.iterator = iterator


# Use the ModelChoiceFieldChooseIterato class instead and then remove this
class RootAndChildrenModelChoiceField(ModelChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.iterator = RootAndChildrenModelChoiceIterator
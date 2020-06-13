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


class AjaxModelChoiceField(ModelChoiceField):
    def __init__(self, *args, **kwargs):
        queryset = kwargs["get_queryset"]
        querysets = {}
        querysets["get_queryset"] = kwargs.pop("get_queryset")
        querysets["load_queryset"] = kwargs.pop("load_queryset")
        querysets["post_queryset"] = kwargs.pop("post_queryset")
        querysets["inst_queryset"] = kwargs.pop("inst_queryset")
        searchable_fields = kwargs.pop("searchable_fields")
        super().__init__(queryset, *args, **kwargs)
        for queryset in querysets:
            setattr(self, queryset, querysets[queryset])
        self.searchable_fields = searchable_fields


class RootAndLeavesModelChoiceField(ModelChoiceField):

    def __init__(self, queryset, *args, **kwargs):
        self.iterator = RootAndLeavesModelChoiceIterator
        super().__init__(queryset, *args, **kwargs)


class AjaxRootAndLeavesModelChoiceField(AjaxModelChoiceField, RootAndLeavesModelChoiceField):
    pass

    # PREVIOUSLY JUST HAD THIS -
    # def __init__(self, *args, **kwargs):
    #     queryset = kwargs["get_queryset"]
    #     querysets = {}
    #     querysets["get_queryset"] = kwargs.pop("get_queryset")
    #     querysets["load_queryset"] = kwargs.pop("load_queryset")
    #     querysets["post_queryset"] = kwargs.pop("post_queryset")
    #     querysets["inst_queryset"] = kwargs.pop("inst_queryset")
    #     searchable_fields = kwargs.pop("searchable_fields")
    #     super().__init__(queryset, *args, **kwargs)
    #     for queryset in querysets:
    #         setattr(self, queryset, querysets[queryset])
    #     self.searchable_fields = searchable_fields

from accountancy.widgets import ExtraFieldsMixin
from django.forms.widgets import CheckboxSelectMultiple

from settings.helpers import PermissionUI

class WidgetPermissionUI(PermissionUI):

    def __init__(self):
        self.groups = {}

    def create_table_row(self, app, section, obj, actions):
        return {
            "module": app,
            "section": section,
            "object": obj,
            "create_field": actions["create"],
            "edit_field": actions["edit"],
            "view_field": actions["view"],
            "void_field": actions["void"]
        }

    def get_app_from_perm(self, option):
        return option["attrs"]["data-option-attrs"]["data-content_type__app_label"]

    def get_codename_from_perm(self, option):
        return option["attrs"]["data-option-attrs"]["data-codename"]

class CheckboxSelectMultipleWithDataAttr(ExtraFieldsMixin, CheckboxSelectMultiple):
    template_name = "settings/perm_table.html"
    option_template_name = "settings/perm_object_edit.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        # optgroups is a list of tuples
        # each tuple is (group_name, options, index)
        # group is always None for us
        # index is just a counter used for creating id attrs - we do not care about this
        # normally django passes the options to a template
        # we loops through the options and creates the option html elements
        # because we don't have groups each options list contains only a single option
        # our task here is to create options based
        optgroups = ctx["widget"]["optgroups"]
        w = WidgetPermissionUI()
        for group, options, index in optgroups:
            w.add_to_group(options[0])
        rows = w.create_table_rows()
        new_optgroups = []
        for row in rows:
            row["template_name"] = self.option_template_name
            new_optgroup = (
                None, # group name
                row,
                0 # index
            )
            new_optgroups.append(new_optgroup)
        ctx["widget"]["optgroups"] = new_optgroups
        return ctx
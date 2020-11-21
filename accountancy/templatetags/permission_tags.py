import re

from django.template import Library
from django.template.loader import render_to_string

register = Library()


@register.simple_tag(takes_context=True)
def perm_form(context, form):
    create_field = ""
    edit_field = ""
    view_field = ""
    void_field = ""
    for bound_field in form:
        match = re.search('name="(.*)"', str(bound_field))
        widget_name_attr = match[1]
        # name attr on widget element is the permission code name
        matches = re.match("^(.*?)-(.*?)_(.*?)_(.*?)$", widget_name_attr)
        action = matches[2]
        if action == "create":
            create_field = bound_field
        elif action == "edit" or action == "change":
            edit_field = bound_field
        elif action == "view":
            view_field = bound_field
        elif action == "delete" or action == "void":
            void_field = bound_field
    ctx = {
        "create_field": create_field,
        "edit_field": edit_field,
        "view_field": view_field,
        "void_field": void_field
    }
    return render_to_string("settings/perm_form.html", context=ctx)

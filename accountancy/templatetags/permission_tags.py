import re

from django.template import Library
from django.template.loader import render_to_string

register = Library()


@register.simple_tag(takes_context=True)
def perm_form(context, form):
    """
    We need to group the form fields -
        module
        section
        object
    """
    groups = {}
    """
    E.g.

    groups = {
        "Purchase": {
            "Transaction": {
                "Create Invoice": {
                    "create" : form_field,
                    "edit": form_field,
                    "view": form_field,
                    "void": form_field
                }
            }
        },
        "Sales": {
            "Transaction": {
                "Create Invoice"
            }
        }
    }
    """
    for bound_field in form.iteritems():
        # bound_field_str = str(bound_field)
        # print(bound_field_str)
        print(1)
    # print(1)
    # app = re.search('data-content_type__app_label="(.*?)"', bound_field_str)[1]
    # print(app)
    #     codename = re.search('data-codename="(.*?)"', bound_field_str)[1]
    #     print(codename)
    #     """
    #     There are two kinds of permissions -

    #         Custom -

    #             <action>_<object>_<section>

    #         Built in -
                
    #             <action>_<object>
    #     """
    #     action_object = re.match("(.*?)_(.*)", codename)
    #     action = action_object[1]
    #     print(action)
    #     obj = action_object[2]
    #     print(obj)
    #     section = "maintenence"
    #     m = re.match("(.*?)_(.*)", obj)
    #     if m:
    #         # so custom, not built in
    #         obj = m[0]
    #         section = m[1]
    #     if app not in groups:
    #         groups[app] = {}
    #     if section not in groups[app]:
    #         groups[app][section] = {}
    #     if obj not in groups[app][section]:
    #         groups[app][section][obj] = {
    #             "create": "",
    #             "edit": "",
    #             "view": "",
    #             "void": ""
    #         }
        
    #     # built in perms use different words for same actions
    #     # so normalise here
    #     if action == "add":
    #         action = "create"
    #     if action == "change":
    #         action = "edit"
    #     if action == "delete":
    #         action = "void"

    #     groups[app][section][obj][action] = bound_field

    # print(groups)
    
    # rows = []
    # for app, sections in groups.items():
    #     for section, objects in sections.items():
    #         for obj, actions in objects.items():
    #             row = {}
    #             row["module"] = app
    #             row["section"] = section
    #             row["object"] = obj
    #             row["create_field"] = actions["create"]
    #             row["edit_field"] = actions["edit"]
    #             row["view_field"] = actions["view"]
    #             row["void_field"] = actions["void"]
    #             rows.append(row)
    # ctx = {
    #     "rows": {}
    # }
    # return render_to_string("settings/perm_form.html", context=ctx)
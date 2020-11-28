import re

class PermissionUI:
    """
    Help with arranging the perms into groups for the UI
    """
    def __init__(self, group_perms):
        self.group_perms = group_perms
        self.groups = {}

    def create_checkbox(self, perm):
        if perm:
            if self.group_perms and perm in self.group_perms:
                checked = True
            else:
                checked = False
            return "<input type='checkbox' " + ( "checked" if checked else "" ) + " disabled>"
        else:
            return ""

    def create_table_row(self, app, section, obj, actions):
        return {
            "module": app,
            "section": section,
            "object": obj,
            "create_field": self.create_checkbox(actions["create"]),
            "edit_field": self.create_checkbox(actions["edit"]),
            "view_field": self.create_checkbox(actions["view"]),
            "void_field": self.create_checkbox(actions["void"])
        }

    def create_table_rows(self):
        rows = []
        for app, sections in self.groups.items():
            for section, objects in sections.items():
                for obj, actions in objects.items():
                    row = self.create_table_row(app, section, obj, actions)
                    rows.append(row)
        return rows

    def get_app_from_perm(self, perm):
        return perm.content_type.app_label

    def get_codename_from_perm(self, perm):
        return perm.codename

    def add_to_group(self, perm):
        app = self.get_app_from_perm(perm)
        codename = self.get_codename_from_perm(perm)
        """
        There are two kinds of permissions -

            Custom -

                <action>_<object>_<section>

            Built in -
                
                <action>_<object>
        """
        action_object = re.match("(.*?)_(.*)", codename)
        action = action_object[1]
        obj = action_object[2]
        section = "maintenence"
        m = re.match("(.*)_(.*)", obj)
        if m:
            # so custom, not built in
            obj = m[1]
            section = m[2]
        if app not in self.groups:
            self.groups[app] = {}
        if section not in self.groups[app]:
            self.groups[app][section] = {}
        if obj not in self.groups[app][section]:
            self.groups[app][section][obj] = {
                "create": "",
                "edit": "",
                "view": "",
                "void": ""
            }
        # built in perms use different words for same actions
        # so normalise here
        if action == "add":
            action = "create"
        if action == "change":
            action = "edit"
        if action == "delete":
            action = "void"
        self.groups[app][section][obj][action] = perm
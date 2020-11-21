import re

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from purchases.forms import PurchasePermissionForm
from purchases.models import PurchaseHeader


class ModelPermissions:
    module = "PL"
    models = [
        {
            "model": PurchaseHeader,
            "exclude": [
                "add_purchaseheader",
                "change_purchaseheader",
                "delete_purchaseheader",
                "view_purchaseheader"
            ]
        },
    ]

    @classmethod
    def get_perms_for_users(cls):
        # ContentType.objects.get_for_model uses a cache so does not the db each time
        model_content_types = {model["model"]: ContentType.objects.get_for_model(
            model["model"]) for model in cls.models}
        perms = Permission.objects.filter(
            content_type__in=model_content_types.values())
        exclusions = {model_content_types[model["model"]].pk: model.get("exclude")
                      for model in cls.models}
        return [
            perm
            for perm in perms
            if exclusions.get(perm.content_type_id)
            and perm.codename not in exclusions[perm.content_type_id]
        ]


    @classmethod
    def get_forms_for_perms(cls, perms):
        ui = {}
        for perm in perms:
            codename = perm.codename 
            matches = re.match("^(.*?)_(.*)_(.*)$", codename)
            full_codename = matches[0]
            action = matches[1]
            perm_thing = matches[2]
            section = matches[3]
            if section not in ui:
                ui[section] = {}
            if perm_thing not in ui[section]:
                ui[section][perm_thing] = []
            ui[section][perm_thing].append(perm)        
        forms = {}
        for section in ui:
            for perm_thing in ui[section]:
                perms = ui[section][perm_thing]
                form = PurchasePermissionForm(perms=perms)
                if section not in forms:
                    forms[section] = {}
                forms[section][perm_thing] = form
        return forms
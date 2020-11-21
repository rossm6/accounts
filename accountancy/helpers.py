import re
from datetime import date
from decimal import Decimal
from functools import reduce
from itertools import groupby
from uuid import uuid4

from django import forms
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from more_itertools import pairwise
from simple_history import register
from simple_history.models import HistoricalRecords
from simple_history.utils import (get_change_reason_from_object,
                                  get_history_manager_for_model)

from accountancy.signals import audit_post_delete

DELETED_HISTORY_TYPE = "-"


"""
Permission Forms i.e. checkboxes shown in the UI for selecting what the user can and cannot do.

Each form is part of a section in the UI.

E.g.


Purchase Ledger
    Enquiry
        View Transactions
    Reports
        Aged Creditors
    Transaction
        Brought Forward Invoice


So ViewTransactions, Aged Creditors and Brought Forward invoice each have a form.

"""


class BasePermissionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        perms = kwargs.pop("perms")
        super().__init__(*args, **kwargs)
        self.field_to_perm = {}
        for perm in perms:
            self.fields[perm.codename] = forms.BooleanField(
                required=False, initial=False)
            # we need this when we have data bound to the form
            # when saving we need the perm pks
            self.field_to_perm[perm.codename] = perm


class BaseModelPermissions:

    @classmethod
    def get_perms_for_users(cls):
        from django.contrib.contenttypes.models import ContentType
        # ContentType.objects.get_for_model uses a cache so does not the db each time
        model_content_types = {
            model["model"]:
            ContentType.objects.get_for_model(
                model["model"],
                for_concrete_model=model.get("for_concrete_model", True)
            )
            for model in cls.models
        }
        cls.model_content_types = model_content_types
        from django.contrib.auth.models import Permission
        perms = Permission.objects.filter(
            content_type__in=model_content_types.values())
        exclusions = {model_content_types[model["model"]].pk: model.get("exclude", [])
                      for model in cls.models}
        return [
            perm
            for perm in perms
            if perm.codename not in exclusions[perm.content_type_id]
        ]

    @classmethod
    def get_section(cls, perm):
        # by convention the section is the last word after the last underscore in
        # the codename of the permission.  Sometimes this may not be though.
        section = None
        if hasattr(cls, "model_content_types"):
            model_content_types = cls.model_content_types
        else:
            model_content_types = {model["model"]: ContentType.objects.get_for_model(
                model["model"]) for model in cls.models}
            cls.model_content_types = model_content_types
        reverse_dict = {content_type_obj.pk: model for model,
                        content_type_obj in model_content_types.items()}
        model = reverse_dict[perm.content_type_id]
        for m in cls.models:
            if m["model"] is model:
                section = m.get("section")
                break
        return section

    @classmethod
    def get_initial(cls, perms, current_perms):
        initial = {}
        for perm in current_perms:
            if perm in perms:
                initial[perm.codename] = True
        return initial

    @classmethod
    def get_forms_for_perms(cls, perms, current_perms, **kwargs):
        ui = {}
        for perm in perms:
            codename = perm.codename
            matches = re.match("^(.*?)_(.*)_(.*)$", codename)
            if matches:
                # custom permissions
                full_codename = matches[0]
                action = matches[1]
                perm_thing = matches[2]
                section = matches[3]
            else:
                # built in django permissions
                matches = re.match("^(.*?)_(.*)$", codename)
                full_codename = matches[0]
                action = matches[1]
                perm_thing = matches[2]
                section = cls.get_section(perm)
            if section not in ui:
                ui[section] = {}
            if perm_thing not in ui[section]:
                ui[section][perm_thing] = []
            ui[section][perm_thing].append(perm)
        forms = {}
        for section in ui:
            for perm_thing in ui[section]:
                perms = ui[section][perm_thing]
                if data := kwargs.get("data"):
                    form = BasePermissionForm(data, perms=perms, prefix=cls.prefix, initial=cls.get_initial(perms, current_perms))
                else:
                    form = BasePermissionForm(perms=perms, prefix=cls.prefix, initial=cls.get_initial(perms, current_perms))
                if section not in forms:
                    forms[section] = {}
                forms[section][perm_thing] = form
        return forms


def get_action(history_type):
    if history_type == "+":
        return "Create"
    elif history_type == "~":
        return "Update"
    elif history_type == "-":
        return "Delete"


def get_historical_change(obj1, obj2, pk_name="id"):
    audit = {}
    if not obj1:
        # then obj2 should be the creation audit log
        d = obj2.__dict__
        for field, value in d.items():
            if not re.search("^history_", field) and not re.search("^_", field):
                audit[field] = {
                    "old": "",  # this since is the first audit log
                    "new": str(value),
                }
    else:
        if obj2.history_type != "-":
            # i.e. not deleted
            diff = obj2.diff_against(obj1)
            if not diff.changes:
                # simple_history creates an audit log every time
                # you save.  Of course I also create the records
                # through bulk_create, bulk_update
                # So duplicates, or unnecessary even, logs are created
                # Periodically we ought to remove these from the DB
                # Regardless, never show them in the UI
                return None
            for change in diff.changes:
                audit[change.field] = {
                    "old": str(change.old),
                    "new": str(change.new),
                }
        else:
            # like the audit for creation, only values should show in old column
            d = obj2.__dict__
            for field, value in d.items():
                if not re.search("^history_", field) and not re.search("^_", field):
                    audit[field] = {
                        "old": str(value),
                        "new": ""
                    }

    audit["meta"] = {
        "AUDIT_id": obj2.history_id,
        "AUDIT_action": get_action(obj2.history_type),
        "AUDIT_user": obj2.history_user_id,
        "AUDIT_date": obj2.history_date,
        "object_pk": getattr(obj2, pk_name)
    }

    return audit


def get_all_historical_changes(objects, pk_name="id"):
    """
    The `objects` are assumed ordered from oldest to most recent.
    """
    changes = []
    if objects:
        objects = list(objects)
        objects.insert(0, None)
        for obj1, obj2 in pairwise(objects):
            change = get_historical_change(obj1, obj2, pk_name)
            if change:
                # because change could be `None` which points to a duplicate audit log
                # see the note in `get_historical_change` of this same module
                changes.append(change)

    user_ids = [change["meta"]["AUDIT_user"]
                for change in changes if type(change["meta"]["AUDIT_user"]) is int]
    users = get_user_model().objects.filter(
        pk__in=[user_id for user_id in user_ids])
    users_map = {user.pk: user for user in users}

    for change in changes:
        change["meta"]["AUDIT_user"] = users_map.get(
            change["meta"]["AUDIT_user"])

    return changes


def disconnect_simple_history_receiver_for_post_delete_signal(model):
    """
    We don't want the post_delete signal from the `simple_history` package.
    This function removes it for the given model.
    """
    receiver_objects = models.signals.post_delete._live_receivers(model)
    if receiver_objects:
        for receiver in receiver_objects:
            if receiver.__self__.__class__.__name__ == HistoricalRecords.__name__:
                models.signals.post_delete.disconnect(receiver, sender=model)
                break


def create_historical_records(
        objects,
        model,
        history_type,
        batch_size=None,
        default_user=None,
        default_change_reason="",
        default_date=None):
    """
    Very similar to bulk_history_create which is a method of the HistoryManager
    within the simple history package.

    This one though allows the history type to be passed which is necessary because
    we are using a deletion history type.  The manager method only supports create and
    update history types for this method.  We need this because we have created our
    own bulk_delete_with_history below.
    """
    if model._meta.proxy:
        history_manager = get_history_manager_for_model(
            model._meta.proxy_for_model)
    else:
        history_manager = get_history_manager_for_model(model)
    historical_instances = []
    for instance in objects:
        history_user = getattr(
            instance,
            "_history_user",
            default_user or history_manager.model.get_default_history_user(
                instance),
        )
        row = history_manager.model(
            history_date=getattr(
                instance, "_history_date", default_date or timezone.now()
            ),
            history_user=history_user,
            history_change_reason=get_change_reason_from_object(
                instance) or default_change_reason,
            history_type=history_type,
            **{
                field.attname: getattr(instance, field.attname)
                for field in instance._meta.fields
                if field.name not in history_manager.model._history_excluded_fields
            }
        )
        if hasattr(history_manager.model, "history_relation"):
            row.history_relation_id = instance.pk
        historical_instances.append(row)

    return history_manager.bulk_create(
        historical_instances, batch_size=batch_size
    )


def bulk_delete_with_history(objects, model, batch_size=None, default_user=None, default_change_reason="", default_date=None):
    """
    The package `simple_history` does not log what was deleted if the items
    are deleted in bulk.  This does.
    """
    model_manager = model._default_manager
    model_manager.filter(pk__in=[obj.pk for obj in objects]).delete()

    history_type = DELETED_HISTORY_TYPE
    return create_historical_records(
        objects,
        model,
        history_type,
        batch_size=batch_size,
        default_user=default_user,
        default_change_reason=default_change_reason,
        default_date=default_date
    )


class AuditTransaction:
    def __init__(self, header_tran, header_model, line_model, match_model=None):
        self.audit_header_history = header_tran.history.all().order_by("pk")
        self.header_model_pk_name = header_model._meta.pk.name
        # may be empty if payment for example (which has no lines)
        self.audit_lines_history = []
        self.line_model_pk_name = line_model._meta.pk.name
        if header_tran.type in header_tran._meta.model.get_types_requiring_lines():
            self.audit_lines_history = (
                line_model.history.filter(
                    header=header_tran.pk
                ).order_by(line_model._meta.pk.name, "pk")
            )
        if match_model:
            self.audit_matches_history = (
                match_model.history.filter(
                    Q(matched_by=header_tran.pk) | Q(matched_to=header_tran.pk)
                ).order_by(line_model._meta.pk.name, "pk")
            )
            self.match_model_pk_name = match_model._meta.pk.name

    def get_historical_changes(self):
        all_changes = []
        self.audit_header_history_changes = get_all_historical_changes(
            self.audit_header_history, self.header_model_pk_name
        )
        for change in self.audit_header_history_changes:
            change["meta"]["transaction_aspect"] = "header"
        all_changes += self.audit_header_history_changes

        for line_pk, history in groupby(self.audit_lines_history, key=lambda l: getattr(l, self.line_model_pk_name)):
            changes = get_all_historical_changes(
                history, self.line_model_pk_name)
            for change in changes:
                change["meta"]["transaction_aspect"] = "line"
            all_changes += changes

        if hasattr(self, "audit_matches_history"):
            for match_pk, history in groupby(self.audit_matches_history, lambda m: getattr(m, self.match_model_pk_name)):
                changes = get_all_historical_changes(
                    history, self.match_model_pk_name)
                for change in changes:
                    change["meta"]["transaction_aspect"] = "match"
                all_changes += changes

        all_changes.sort(key=lambda c: c["meta"]["AUDIT_date"])
        return all_changes


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

    def __lt__(self, other):
        if type(other) is type(self):
            return str(self) < str(other)
        else:
            return str(self) < other

    def __ge__(self, other):
        if type(other) is type(self):
            return str(self) >= str(other)
        else:
            return str(self) >= other

    def __gt__(self, other):
        if type(other) is type(self):
            return str(self) > str(other)
        else:
            return str(self) > other

    def __str__(self):
        return self.period


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


"""
Temporary until forms and views are refactored
"""


def non_negative_zero_decimal(decimal):
    """
    Avoids negative zero
    """
    if decimal == Decimal(0.00):
        return Decimal(0.00)
    return decimal

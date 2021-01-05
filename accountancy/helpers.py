import re
from datetime import date
from decimal import Decimal
from functools import reduce
from itertools import groupby
from uuid import uuid4

from django import forms
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from more_itertools import pairwise
from simple_history import register
from simple_history.exceptions import AlternativeManagerError
from simple_history.models import HistoricalRecords
from simple_history.utils import (get_change_reason_from_object,
                                  get_history_manager_for_model)

from accountancy.signals import audit_post_delete

DELETED_HISTORY_TYPE = "-"


class JSONBlankDate(date):
    """

    The serializer used by Django when encoding into Json for JsonResponse
    is `DjangoJSONEncoder`
    Per - https://docs.djangoproject.com/en/3.1/topics/serialization/
    And this serializer uses the isoformat method on the date object
    for getting the value for the json.  Per - https://github.com/django/django/blob/master/django/core/serializers/json.py
    This subclass just returns an empty string for the json response.  

    It is used with the creditor and debtor reports.
    A date object is needed to sort the objects based on this but the database value is ''.
    """

    def isoformat(self):
        return ""


def get_action(history_type):
    if history_type == "+":
        return "Create"
    elif history_type == "~":
        return "Update"
    elif history_type == "-":
        return "Delete"


def get_historical_change(obj1, obj2, pk_name="id", **kwargs):
    audit = {}
    ui_audit_fields = kwargs.get("ui_audit_fields", [])
    if not obj1:
        # then obj2 should be the creation audit log
        d = obj2.__dict__
        for field, value in d.items():
            create_audit = {
                "old": "",
                "new": str(value)
            }
            if ui_audit_fields:
                if field in ui_audit_fields:
                    audit[field] = create_audit
            else:
                if not re.search("^history_", field) and not re.search("^_", field):
                    audit[field] = create_audit
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
                edit_audit = {
                    "old": str(change.old),
                    "new": str(change.new),
                }
                if ui_audit_fields:
                    if change.field in ui_audit_fields:
                        audit[change.field] = edit_audit
                else:
                    if not re.search("^history_", change.field) and not re.search("^_", change.field):
                        audit[change.field] = edit_audit
        else:
            # like the audit for creation, only values should show in old column
            d = obj2.__dict__
            for field, value in d.items():
                delete_audit = {
                    "old": str(value),
                    "new": ""
                }
                if ui_audit_fields:
                    if field in ui_audit_fields:
                        audit[field] = delete_audit
                else:
                    if not re.search("^history_", field) and not re.search("^_", field):
                        audit[field] = delete_audit

    audit["meta"] = {
        "AUDIT_id": obj2.history_id,
        "AUDIT_action": get_action(obj2.history_type),
        "AUDIT_user": obj2.history_user_id,
        "AUDIT_date": obj2.history_date,
        "object_pk": getattr(obj2, pk_name)
    }

    return audit


def get_all_historical_changes(objects, pk_name="id", **kwargs):
    """
    The `objects` are assumed ordered from oldest to most recent.
    """
    changes = []
    if objects:
        objects = list(objects)
        objects.insert(0, None)
        for obj1, obj2 in pairwise(objects):
            change = get_historical_change(obj1, obj2, pk_name, **kwargs)
            if change and len([k for k in change.keys() if k != "meta"]):
                # i.e. audits with META info only will exist if only fields not
                # wanted in the UI have changed
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


def bulk_create_with_history(
    objs,
    model,
    batch_size=None,
    default_user=None,
    default_change_reason=None,
    default_date=None,
):
    """
    This is a copy of the utility of the same name from `simple_history`.

    The problem I had was that I need to save a different value to the audit record
    other than the field value sometimes.  This is because the transaction models - header, line,
    and update - all contain field values which have the sign determined by header.type when
    displaying in the UI.  If the values show like this in the UI they should in the audit also.

    I have removed the @ignore_conflicts parameter because we should never ignore conflicts.
    Moreover it seemed to be that doing so would result in a seperate DB hit to get each object
    from the db so we have  the pk.

    Also this utility calls create_historical_records.  In this function we can then implement
    the logic which swaps the field value to the ui field value if need be.
    """
    # Exclude ManyToManyFields because they end up as invalid kwargs to
    # model.objects.filter(...) below.
    exclude_fields = [
        field.name
        for field in model._meta.get_fields()
        if isinstance(field, ManyToManyField)
    ]
    model_manager = model._default_manager
    with transaction.atomic(savepoint=False):
        objs_with_id = model_manager.bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=False
        )
        create_historical_records(
            objs_with_id,
            model,
            "+",
            batch_size=batch_size,
            default_user=default_user,
            default_change_reason=default_change_reason,
            default_date=default_date,
        )
    return objs_with_id


def bulk_update_with_history(
    objs,
    model,
    fields,
    batch_size=None,
    default_user=None,
    default_change_reason=None,
    default_date=None,
    manager=None,
):
    """
    Again like bulk_create_with_history this calls `create_historical_records`
    """
    model_manager = manager or model._default_manager
    if model_manager.model is not model:
        raise AlternativeManagerError(
            "The given manager does not belong to the model.")

    with transaction.atomic(savepoint=False):
        model_manager.bulk_update(objs, fields, batch_size=batch_size)
        create_historical_records(
        objs,
        model,
        "-",
        batch_size=batch_size,
        update=True,
        default_user=default_user,
        default_change_reason=default_change_reason,
        default_date=default_date,
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
        self.header_model = header_model
        self.header_model_pk_name = header_model._meta.pk.name
        # may be empty if payment for example (which has no lines)
        self.audit_lines_history = []
        self.line_model = line_model
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
            self.match_model = match_model

    def get_ui_values(self, history_object, model):
        """
        If a descriptor exists on the model of form <ui_><field_name> get the value
        from it and replace history_object[field_name] with it
        """
        model_attrs = {}
        for field, value in history_object.__dict__.items():
            if not (re.search("^history_", field) or re.search("^_", field)):
                model_attrs[field] = value
        i = model(**model_attrs)
        for f, v in i.__dict__.items():
            if hasattr(i, f"ui_{f}"):
                ui_field_value = getattr(i, f"ui_{f}")
                setattr(history_object, f, ui_field_value)
        return history_object

    def get_historical_changes(self):
        all_changes = []
        self.audit_header_history_changes = get_all_historical_changes(
            [ self.get_ui_values(h, self.header_model) for h in self.audit_header_history], self.header_model_pk_name
        )
        for change in self.audit_header_history_changes:
            change["meta"]["transaction_aspect"] = "header"
        all_changes += self.audit_header_history_changes

        for line_pk, history in groupby(self.audit_lines_history, key=lambda l: getattr(l, self.line_model_pk_name)):
            changes = get_all_historical_changes(
                [ self.get_ui_values(h, self.line_model) for h in history], self.line_model_pk_name)
            for change in changes:
                change["meta"]["transaction_aspect"] = "line"
            all_changes += changes

        if hasattr(self, "audit_matches_history"):
            for match_pk, history in groupby(self.audit_matches_history, lambda m: getattr(m, self.match_model_pk_name)):
                changes = get_all_historical_changes(
                    [ 
                        self.get_ui_values(h, self.match_model) 
                        for h in history
                    ], 
                    self.match_model_pk_name
                )
                for change in changes:
                    change["meta"]["transaction_aspect"] = "match"
                all_changes += changes

        all_changes.sort(key=lambda c: c["meta"]["AUDIT_date"])
        return all_changes


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

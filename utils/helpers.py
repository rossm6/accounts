import re
from functools import reduce
from itertools import groupby

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.fields.reverse_related import ManyToManyRel, ManyToOneRel
from django.utils import timezone
from more_itertools import pairwise
from simple_history.models import HistoricalRecords
from simple_history.utils import (get_change_reason_from_object,
                                  get_history_manager_for_model)

DELETED_HISTORY_TYPE = "-"


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
    The objects are assumed ordered from oldest to most recent
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


def get_deleted_objects(model_objects, audit_logs, pk_field):
    """
    `simple_history` does not support bulk_delete so we bulk_delete
    when we can.  Still we need to cater for objects deleted via
    the admin but might not have been audit logged.

    This helper functions just checkes if an audit log exists
    for an object not in model_objects.

    We assume the audit logs are ordered from oldest to most recent.

    WARNING - logs have the history_type attribute changed if a deletion
    has not been logged.  DO NOT SAVE THIS TO THE DB.
    """
    deleted = {}
    def f(a): return getattr(a, pk_field)
    audits_sorted_by_model_object = sorted(audit_logs, key=f)
    audits_per_model_object = groupby(audits_sorted_by_model_object, key=f)
    audits_per_model_object = {
        pk_field: list(audit_logs)
        for pk_field, audit_logs in audits_per_model_object
    }
    model_map = {obj.pk: obj for obj in model_objects}
    for log in audit_logs:
        pk_value = getattr(log, pk_field)
        if pk_value not in model_map:
            # but has the deletion been logged already?
            deletion_logged = False
            for _log in audits_per_model_object[pk_value]:
                if _log.history_type == DELETED_HISTORY_TYPE:
                    deletion_logged = True
                    break
            if not deletion_logged:
                log.history_type = "-"
                deleted[pk_value] = log
    return deleted


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

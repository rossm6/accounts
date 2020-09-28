import re
from functools import reduce

from django.db import models
from django.db.models.fields.reverse_related import ManyToManyRel, ManyToOneRel
from django.utils import timezone
from more_itertools import pairwise
from simple_history.models import HistoricalRecords
from simple_history.utils import (get_change_reason_from_object,
                                  get_history_manager_for_model)

from sales.models import Customer


def get_historical_change(obj1, obj2):
    audit = {}
    if not obj1:
        # then obj1 should be the creation audit log
        d = obj2.__dict__
        for field, value in d.items():
            if not re.search("^history_", field) and not re.search("^_", field):
                audit[field] = {
                    "old": "",  # this since is the first audit log
                    "new": str(value)
                }
    else:
        diff = obj2.diff_against(obj1)
        for change in diff.changes:
            audit[change.field] = {
                "old": str(change.old),
                "new": str(change.new)
            }
    return audit


def get_all_historical_changes(objects):
    """
    The objects are assumed ordered from oldest to most recent
    """
    changes = []
    if objects:
        objects = list(objects)
        objects.insert(0, None)
        for obj1, obj2 in pairwise(objects):
            changes.append(get_historical_change(obj1, obj2))
    return changes


def get_deleted_objects(model_objects, audit_logs, pk_field):
    """
    `simple_history` does not support bulk_delete so we bulk_delete
    when we can.  Still we need to cater for objects deleted via
    the admin but might not have been audit logged.

    This helper functions just checkes if an audit log exists
    for an object not in model_objects.

    We assume the audit logs are ordered from oldest to most recent.
    """
    deleted = {}
    model_map = {obj.pk: obj for obj in model_objects}
    for log in audit_logs:
        pk_value = getattr(log, pk_field)
        if pk_value not in model_map:
            deleted[pk_value] = log
    return deleted


def disconnect_simple_history_receiver_for_post_delete_signal(model):
    receiver_objects = models.signals.post_delete._live_receivers(model)
    if receiver_objects:
        for receiver in receiver_objects:
            if receiver.__self__.__class__.__name__ == HistoricalRecords.__name__:
                models.signals.post_delete.disconnect(receiver, sender=model)
                break


def bulk_delete_with_history(objects, model, batch_size=None, default_user=None, default_change_reason="", default_date=None):
    """

    The package `simple_history` does not log what was deleted if the items
    are deleted in bulk.  This does.

    Although it isn't great.  Obviously we have to disconnect the receiver
    from the package so we don't get duplicate audit logs which would also
    be extremely expensive.  The downside though is any delete done through
    the admin, or, for that matter, any delete done via code i don't control,
    will not produce an audit log if this has been called already.

    But I could just write code which checks if objects are missing from
    the created audit logs and create delete logs on the fly for the view.
    There wouldn't really be the need to save the logs to the DB.

    Another approach is to perhaps add an attribute / flag to the instance
    to be deleted.  This is based on this answer - https://stackoverflow.com/questions/11179380/pass-additional-parameters-to-post-save-signal
    Not sure it would work with delete though.  Certainly you'd need to pull
    the objects into memory first before deleting.

    """

    disconnect_simple_history_receiver_for_post_delete_signal(model)

    model_manager = model._default_manager
    model_manager.filter(pk__in=[obj.pk for obj in objects]).delete()

    history_manager = get_history_manager_for_model(model)
    history_type = "-"
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

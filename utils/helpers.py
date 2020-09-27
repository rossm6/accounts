from functools import reduce

from django.db import models
from django.utils import timezone
from simple_history.utils import (get_change_reason_from_object,
                                  get_history_manager_for_model)
from simple_history.models import HistoricalRecords

from sales.models import Customer



class TurnSignalOffAndOn:
    """

    Turn off the signal before a task.  Then reconnect the signal.

    It is important to understand however that signals are global in django.
    So if we disconnect, before the reconnection, the signal will be received
    even in other contexts i.e. different requests, different threads.

    I keep this here as a reminder.  But really it is of no use.
    If this concern isn't relevant, just disconnect the signal altogether.

    """
    def __init__(self, signal, receiver, sender, dispatch_uid=None):
        self.signal = signal
        self.receiver = receiver
        self.sender = sender
        self.dispatch_uid = dispatch_uid

    def __enter__(self):
        self.signal.disconnect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid,
            weak=False
        )

    def __exit__(self, type, value, traceback):
        self.signal_connect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid,
            weak=False
        )


def bulk_delete_with_history(objects, model, batch_size=None, default_user=None, default_change_reason="", default_date=None):
    """
    The package `simple_history` does not log what was deleted if the items
    are deleted in bulk.  This does.
    """
    
    # We must ensure the post_delete signal is turned off first
    receiver = None
    receiver_objects = models.signals.post_delete._live_receivers(model)
    if receiver_objects:
        for receiver in receiver_objects:
            if receiver.__self__.__class__.__name__ == HistoricalRecords.__name__:
                models.signals.post_delete.disconnect(receiver, sender=model)
                break

    model_manager = model._default_manager   
    model_manager.filter(pk__in=[obj.pk for obj in objects]).delete()

    # re connect the receiver that was disconnected now that delete has been called on the queryset
    if receiver:
        models.signals.post_delete.connect(receiver, sender=model, weak=False)

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
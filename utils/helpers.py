import re
from decimal import Decimal
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

def non_negative_zero_decimal(decimal):
    """
    Avoids negative zero
    """
    if decimal == Decimal(0.00):
        return Decimal(0.00)
    return decimal


# DO WE REALLY NEED THIS ?
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
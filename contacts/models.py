from uuid import uuid4

from accountancy.helpers import \
    disconnect_simple_history_receiver_for_post_delete_signal
from accountancy.mixins import AuditMixin
from accountancy.signals import audit_post_delete
from django.db import models
from simple_history import register


class Contact(AuditMixin, models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    customer = models.BooleanField(default=False)
    supplier = models.BooleanField(default=False)

    def __str__(self):
        return self.code


register(Contact)
disconnect_simple_history_receiver_for_post_delete_signal(Contact)
audit_post_delete.connect(Contact.post_delete,
                          sender=Contact, dispatch_uid=uuid4())

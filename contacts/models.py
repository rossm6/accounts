from uuid import uuid4

from accountancy.helpers import \
    disconnect_simple_history_receiver_for_post_delete_signal
from accountancy.mixins import AuditMixin
from accountancy.signals import audit_post_delete
from django.db import models
from django.shortcuts import reverse
from simple_history import register


class Contact(AuditMixin, models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    customer = models.BooleanField(default=False)
    supplier = models.BooleanField(default=False)

    def __str__(self):
        return self.code

    def get_absolute_url(self):
        return reverse("contacts:detail", kwargs={"pk": self.pk})

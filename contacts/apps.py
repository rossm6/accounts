from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class ContactsConfig(AuditMixin, AppConfig):
    name = 'contacts'

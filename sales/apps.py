from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class SalesConfig(AuditMixin, AppConfig):
    name = 'sales'

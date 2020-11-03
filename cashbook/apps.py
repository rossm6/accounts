from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class CashbookConfig(AuditMixin, AppConfig):
    name = 'cashbook'

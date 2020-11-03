from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class PurchasesConfig(AuditMixin, AppConfig):
    name = 'purchases'
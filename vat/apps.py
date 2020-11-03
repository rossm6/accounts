from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class VatConfig(AuditMixin, AppConfig):
    name = 'vat'

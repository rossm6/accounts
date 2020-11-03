from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class NominalsConfig(AuditMixin, AppConfig):
    name = 'nominals'

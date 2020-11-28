from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class ControlsConfig(AuditMixin, AppConfig):
    name = 'controls'

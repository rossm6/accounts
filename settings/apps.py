from accountancy.mixins import AuditMixin
from django.apps import AppConfig


class SettingsConfig(AuditMixin, AppConfig):
    name = 'settings'

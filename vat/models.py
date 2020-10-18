from django.apps import apps
from django.db import models
from simple_history import register

from accountancy.models import MultiLedgerTransactions


class Vat(models.Model):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=30)
    rate = models.DecimalField(
        decimal_places=2,
        max_digits=10,
        default=0
    )
    registered = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name} - {self.rate}%"


class ModuleTypes:
    def __iter__(self):
        model = apps.get_model(app_label="nominals",
                               model_name="NominalTransaction")
        all_module_types = model.all_module_types
        for tran_type in all_module_types:
            yield tran_type


class VatTransaction(MultiLedgerTransactions):
    vat_types = [
        ("i", "Input"),
        ("o", "Output")
    ]
    tran_type = models.CharField(max_length=10, choices=ModuleTypes())
    vat_type = models.CharField(max_length=2, choices=vat_types)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'header', 'line', 'field'], name="vat_unique_batch")
        ]

    @classmethod
    def fields_to_update(cls):
        return [
            "value",
            "ref",
            "period",
            "date",
            "tran_type",
            "vat_type"            
        ]
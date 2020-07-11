from django.db import models

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
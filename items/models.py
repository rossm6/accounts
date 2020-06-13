from django.db import models

class Item(models.Model):
    code = models.CharField(max_length=10)
    description = models.CharField(max_length=225)

    def __str__(self):
        return f"{self.code}:{self.description}"
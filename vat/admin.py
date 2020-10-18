from django.contrib import admin

from .models import Vat, VatTransaction

admin.site.register(Vat)
admin.site.register(VatTransaction)
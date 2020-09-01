from django.contrib import admin

from .models import NominalHeader, NominalLine, NominalTransaction, Nominal

admin.site.register(NominalHeader)
admin.site.register(NominalLine)
admin.site.register(NominalTransaction)
admin.site.register(Nominal)
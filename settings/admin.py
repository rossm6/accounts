from django.contrib import admin

from settings.models import FinancialYear, Period

admin.site.register(FinancialYear)
admin.site.register(Period)
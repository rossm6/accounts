from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Customer, SaleHeader, SaleLine, SaleMatching

admin.site.register(SaleHeader)
admin.site.register(SaleLine)
admin.site.register(SaleMatching)
admin.site.register(Customer, SimpleHistoryAdmin)

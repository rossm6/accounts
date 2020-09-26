from django.contrib import admin

from .models import SaleHeader, SaleLine, SaleMatching, Customer

from simple_history.admin import SimpleHistoryAdmin

admin.site.register(SaleHeader)
admin.site.register(SaleLine)
admin.site.register(SaleMatching)
admin.site.register(Customer, SimpleHistoryAdmin)

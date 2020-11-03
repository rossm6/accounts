from django.contrib import admin

from .models import CashBook, CashBookHeader, CashBookLine, CashBookTransaction

admin.site.register(CashBookHeader)
admin.site.register(CashBookLine)
admin.site.register(CashBook)
admin.site.register(CashBookTransaction)

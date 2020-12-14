from django.contrib import admin

from users.models import Lock, UserSession

admin.site.register(Lock)
admin.site.register(UserSession)

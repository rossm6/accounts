"""proj URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path, re_path, reverse_lazy
from django.views.generic.base import RedirectView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cashbook/', include("cashbook.urls")),
    path('contacts/', include("contacts.urls")),
    path('dashboard/', include("dashboard.urls")),
    path('nominals/', include("nominals.urls")),
    path('purchases/', include("purchases.urls")),
    path('sales/', include("sales.urls")),
    path('users/', include("users.urls")),
    path('users/', include("django.contrib.auth.urls")),
    path('vat/', include("vat.urls")),
    path('', RedirectView.as_view(url=reverse_lazy(
        "dashboard:dashboard")), name="home")
]
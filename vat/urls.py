from django.urls import path

from vat.views import LoadVatCodes

app_name = "vat"
urlpatterns = [
    path("load_vat_codes", LoadVatCodes.as_view(), name="load_vat_codes"),
]
from django.urls import path

from vat.views import (LoadVatCodes, VatCreate, VatDetail, VatList,
                       VatTransactionEnquiry, VatUpdate)

app_name = "vat"
urlpatterns = [
    path("load_vat_codes", LoadVatCodes.as_view(), name="load_vat_codes"),
    path("vat_detail/<int:pk>", VatDetail.as_view(), name="vat_detail"),
    path("vat_create", VatCreate.as_view(), name="vat_create"),
    path("vat_edit/<int:pk>", VatUpdate.as_view(), name="vat_edit"),
    path("vat_list", VatList.as_view(), name="vat_list"),
    path("transactions", VatTransactionEnquiry.as_view(), name="transaction_enquiry"),
]

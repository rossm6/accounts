from django.urls import path

from contacts.views import (ContactListView, CreateCustomer, CreateSupplier,
                            CustomerDetail, CustomerUpdate, SupplierDetail,
                            SupplierUpdate)

app_name = "contacts"
urlpatterns = [
    path("", ContactListView.as_view(), name="contact_list"),
    path("create_customer", CreateCustomer.as_view(), name="create_customer"),
    path("create_supplier", CreateSupplier.as_view(), name="create_supplier"),
    path("customer/<int:pk>", CustomerDetail.as_view(), name="customer_detail"),
    path("supplier/<int:pk>", SupplierDetail.as_view(), name="supplier_detail"),
    path("edit_customer/<int:pk>", CustomerUpdate.as_view(), name="edit_customer"),
    path("edit_supplier/<int:pk>", SupplierUpdate.as_view(), name="edit_supplier"),
]

from django.urls import path

from .views import (CreateTransaction, EditTransaction, TransactionEnquiry,
                    ViewTransaction, VoidTransaction)

app_name = "cashbook"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
]

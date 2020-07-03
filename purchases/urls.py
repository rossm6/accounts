from django.urls import path

from .views import (LoadMatchingTransactions, LoadSuppliers, create, index,
                    load_options, validate_choice, CreateTransaction, edit, TransactionEnquiry)

app_name = "purchases"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", edit, name="edit"),
    path("index", index, name="index"),
    path("load_matching_transactions", LoadMatchingTransactions.as_view(), name="load_matching_transactions"),
    path("load_options", load_options, name="load_options"),
    path("load_suppliers", LoadSuppliers.as_view(), name="load_suppliers"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice")
]
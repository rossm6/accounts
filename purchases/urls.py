from django.urls import path

from .views import (CreateTransaction, EditTransaction,
                    LoadMatchingTransactions, LoadSuppliers,
                    TransactionEnquiry, load_options, validate_choice, create_on_the_fly_view)

app_name = "purchases"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("create_on_the_fly", create_on_the_fly_view, name="create_on_the_fly"),
    path("load_matching_transactions", LoadMatchingTransactions.as_view(), name="load_matching_transactions"),
    path("load_options", load_options, name="load_options"),
    path("load_suppliers", LoadSuppliers.as_view(), name="load_suppliers"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice")
]

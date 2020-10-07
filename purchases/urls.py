from django.urls import path

from .views import (AgeCreditorsReport, CreateTransaction, EditTransaction,
                    LoadPurchaseMatchingTransactions, LoadSuppliers,
                    TransactionEnquiry, ViewTransaction, VoidTransaction)

app_name = "purchases"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("creditors_report", AgeCreditorsReport.as_view(), name="creditors_report"),
    path("load_matching_transactions", LoadPurchaseMatchingTransactions.as_view(),
         name="load_matching_transactions"),
    path("load_suppliers", LoadSuppliers.as_view(), name="load_suppliers"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
]

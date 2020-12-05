from django.urls import path

from .views import (AgeDebtorsReport, CreateTransaction, EditTransaction,
                    LoadCustomers, LoadSaleMatchingTransactions,
                    TransactionEnquiry, ViewTransaction, VoidTransaction)

app_name = "sales"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void/<int:pk>", VoidTransaction.as_view(), name="void"),
    path("debtors_report", AgeDebtorsReport.as_view(), name="debtors_report"),

    path("load_matching_transactions", LoadSaleMatchingTransactions.as_view(),
         name="load_matching_transactions"),
    path("load_customers", LoadCustomers.as_view(), name="load_customers"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
]

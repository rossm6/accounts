from django.urls import path

from .views import (AgeCreditorsReport, CreateTransaction, EditTransaction,
                    LoadPurchaseMatchingTransactions, LoadSuppliers,
                    TransactionEnquiry, ViewTransaction, VoidTransaction,
                    create_on_the_fly_view, load_options, validate_choice,
                    validate_forms_by_ajax, LoadVatCodes, LoadNominals)

app_name = "purchases"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("creditors_report", AgeCreditorsReport.as_view(), name="creditors_report"),

    path("create_on_the_fly", create_on_the_fly_view, name="create_on_the_fly"),
    path("load_matching_transactions", LoadPurchaseMatchingTransactions.as_view(),
         name="load_matching_transactions"),
    path("load_options", load_options, name="load_options"),
    path("load_suppliers", LoadSuppliers.as_view(), name="load_suppliers"),

    path("load_nominals", LoadNominals.as_view(), name="load_nominals"),
    path("load_vat_codes", LoadVatCodes.as_view(), name="load_vat_codes"),

    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice"),
    path("validate_forms_by_ajax", validate_forms_by_ajax, name="validate_forms_by_ajax")
]

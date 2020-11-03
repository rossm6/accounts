from django.urls import path

from .views import (CreateTransaction, EditTransaction, LoadNominal,
                    NominalCreate, NominalDetail, NominalEdit, NominalList,
                    TransactionEnquiry, TrialBalance, ViewTransaction,
                    VoidTransaction)

app_name = "nominals"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("trial_balance", TrialBalance.as_view(), name="trial_balance"),

    path("nominals_list", NominalList.as_view(), name="nominals_list"),
    path("nominal_detail/<int:pk>", NominalDetail.as_view(), name="nominal_detail"),
    path("nominal_edit/<int:pk>", NominalEdit.as_view(), name="nominal_edit"),
    path("nominal_create", NominalCreate.as_view(), name="nominal_create"),

    path("load_nominals", LoadNominal.as_view(), name="load_nominals"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
]

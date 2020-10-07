from django.urls import path

from .views import (CreateTransaction, EditTransaction, LoadNominal,
                    NominalList, TransactionEnquiry, TrialBalance,
                    ViewTransaction, VoidTransaction, create_on_the_fly_view,
                    load_options, validate_choice, NominalDetail, NominalEdit, NominalCreate)

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

    path("create_on_the_fly", create_on_the_fly_view, name="create_on_the_fly"),
    path("load_options", load_options, name="load_options"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice"),
]

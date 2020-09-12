from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import (CreateNominalJournal, CreateTransaction,
                    EditNominalJournal, EditTransaction, NominalDetail,
                    NominalList, NominalTransactionDetail,
                    NominalTransactionList, TransactionEnquiry,
                    ViewTransaction, VoidTransaction, api_root,
                    create_on_the_fly_view, load_options, validate_choice)

app_name = "nominals"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("create_on_the_fly", create_on_the_fly_view, name="create_on_the_fly"),
    path("load_options", load_options, name="load_options"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice"),

    # REST
    path("", api_root),
    path("nominal-transaction-list", NominalTransactionList.as_view(),
         name="nominal-transaction-list"),
    path("nominal-transaction-detail/<int:pk>/", NominalTransactionDetail.as_view(),
         name="nominal-transaction-detail"),
    path("nominal-transaction-create", CreateNominalJournal.as_view(),
         name="nominal-transaction-create"),
    path("nominal-transaction-edit/<int:pk>/", EditNominalJournal.as_view(),
         name="nominal-transaction-edit"),

    path("nominal-list", NominalList.as_view(), name="nominal-list"),
    path('nominals/<int:pk>/', NominalDetail.as_view(), name="nominal-detail"),
]

urlpatterns = format_suffix_patterns(urlpatterns)

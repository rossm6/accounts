from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import (CreateTransaction, EditTransaction, TransactionEnquiry,
                    ViewTransaction, VoidTransaction, create_on_the_fly_view,
                    load_options, nominal_detail, nominal_list,
                    validate_choice)

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
    path("nominal-list", nominal_list),
    path('nominals/<int:pk>/', nominal_detail),
]

urlpatterns = format_suffix_patterns(urlpatterns)

from django.urls import path

from .views import (CreateTransaction, TransactionEnquiry,
                    create_on_the_fly_view, load_options, validate_choice)

app_name = "nominals"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    # path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    # path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    # path("void", void, name="void"),
    path("create_on_the_fly", create_on_the_fly_view, name="create_on_the_fly"),
    path("load_options", load_options, name="load_options"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),
    path("validate_choice", validate_choice, name="validate_choice")
]

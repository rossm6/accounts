from django.urls import path

from .views import create, load_options, LoadSuppliers, validate_choice, LoadMatchingTransactions

app_name = "purchases"
urlpatterns = [
    path("create", create, name="create"),
    path("load_matching_transactions", LoadMatchingTransactions.as_view(), name="load_matching_transactions"),
    path("load_options", load_options, name="load_options"),
    path("load_suppliers", LoadSuppliers.as_view(), name="load_suppliers"),
    path("validate_choice", validate_choice, name="validate_choice")
]

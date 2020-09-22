from django.urls import path

from contacts.views import ContactListView, CreateCustomer

app_name = "contacts"
urlpatterns = [
    path("", ContactListView.as_view(), name="contact_list"),
    path("create_customer", CreateCustomer.as_view(), name="create_customer"),
]

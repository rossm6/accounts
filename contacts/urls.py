from django.urls import path

from contacts.views import (ContactDetail, ContactListView, ContactUpdate,
                            CreateContact)

app_name = "contacts"
urlpatterns = [
    path("", ContactListView.as_view(), name="list"),
    path("create", CreateContact.as_view(), name="create"),
    path("<int:pk>", ContactDetail.as_view(), name="detail"),
    path("edit/<int:pk>", ContactUpdate.as_view(), name="edit"),
]

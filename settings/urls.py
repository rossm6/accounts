from django.urls import path

from settings.views import (GroupDetail, GroupsList, GroupUpdate, SettingsView,
                            UsersList, UserDetail)

app_name = "settings"
urlpatterns = [
    path("", SettingsView.as_view(), name="index"),
    path("groups/", GroupsList.as_view(), name="groups"),
    path("groups/edit/<int:pk>", GroupUpdate.as_view(), name="group_edit"),
    path("groups/view/<int:pk>", GroupDetail.as_view(), name="group_view"),
    path("users/", UsersList.as_view(), name="users"),
    path("users/view/<int:pk>", UserDetail.as_view(), name="user_view"),
]
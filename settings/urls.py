from django.urls import path

from settings.views import GroupsView, SettingsView, UsersView, GroupDetail

app_name = "settings"
urlpatterns = [
    path("", SettingsView.as_view(), name="index"),
    path("groups/", GroupsView.as_view(), name="groups"),
    path("groups/view/<int:pk>", GroupDetail.as_view(), name="group_view"),
    path("users/", UsersView.as_view(), name="users"),
]

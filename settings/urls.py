from django.urls import path

from settings.views import (FinancialYearCreate, FinancialYearDetail,
                            FinancialYearEdit, FinancialYearList, GroupDetail,
                            GroupsList, GroupUpdate, SettingsView, UserDetail,
                            UserEdit, UsersList)

app_name = "settings"
urlpatterns = [
    path("", SettingsView.as_view(), name="index"),
    path("financial_year/", FinancialYearList.as_view(), name="fy_list"),
    path("financial_year/create", FinancialYearCreate.as_view(), name="fy_create"),
    path("financial_year/edit/<int:pk>",
         FinancialYearEdit.as_view(), name="fy_edit"),
    path("financial_year/view/<int:pk>",
         FinancialYearDetail.as_view(), name="fy_view"),
    path("groups/", GroupsList.as_view(), name="groups"),
    path("groups/edit/<int:pk>", GroupUpdate.as_view(), name="group_edit"),
    path("groups/view/<int:pk>", GroupDetail.as_view(), name="group_view"),
    path("users/", UsersList.as_view(), name="users"),
    path("users/edit/<int:pk>", UserEdit.as_view(), name="user_edit"),
    path("users/view/<int:pk>", UserDetail.as_view(), name="user_view"),
]

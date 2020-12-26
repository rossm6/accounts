from django.urls import path

from controls.views import (FinancialYearCreate, FinancialYearDetail,
                            FinancialYearList, GroupCreate, GroupDetail,
                            GroupsList, GroupUpdate, ControlsView, UserCreate,
                            UserDetail, UserEdit, UsersList)

app_name = "controls"
urlpatterns = [
    path("", ControlsView.as_view(), name="index"),
    path("financial_year/", FinancialYearList.as_view(), name="fy_list"),
    path("financial_year/create", FinancialYearCreate.as_view(), name="fy_create"),
    path("financial_year/view/<int:pk>",
         FinancialYearDetail.as_view(), name="fy_view"),
    path("groups/", GroupsList.as_view(), name="groups"),
    path("groups/create", GroupCreate.as_view(), name="group_create"),
    path("groups/edit/<int:pk>", GroupUpdate.as_view(), name="group_edit"),
    path("groups/view/<int:pk>", GroupDetail.as_view(), name="group_view"),
    path("users/", UsersList.as_view(), name="users"),
    path("users/create", UserCreate.as_view(), name="user_create"),
    path("users/edit/<int:pk>", UserEdit.as_view(), name="user_edit"),
    path("users/view/<int:pk>", UserDetail.as_view(), name="user_view"),
]

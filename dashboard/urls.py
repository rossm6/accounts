from django.urls import path

from .views import DashBoard

app_name = "dashboard"
urlpatterns = [
    path("", DashBoard.as_view(), name="dashboard"),
]

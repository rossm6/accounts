from django.urls import path

from users.views import SignUp, validate_forms_by_ajax, profile

app_name = "users"
urlpatterns = [
    path("profile", profile, name="profile"),
    path("signup", SignUp.as_view(), name="signup"),
    path("validate_form", validate_forms_by_ajax, name="validate_form"),
]

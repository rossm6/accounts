from django.urls import path, reverse_lazy
from django.views.generic.base import RedirectView

from users.views import (Profile, SignIn, SignUp, UserPasswordResetConfirmView,
                         UserPasswordResetView, unlock,
                         validate_forms_by_ajax)

app_name = "users"
urlpatterns = [
    path('login', RedirectView.as_view(url=reverse_lazy(
        "users:signin")), name="login"),
    path("password_reset", UserPasswordResetView.as_view(), name="password_reset"),
    path("reset/<uidb64>/<token>/", UserPasswordResetConfirmView.as_view(),
         name="password_reset_confirm"),
    path("profile", Profile.as_view(), name="profile"),
    path("signup", SignUp.as_view(), name="signup"),
    path("signin", SignIn.as_view(), name="signin"),
    path("validate_form", validate_forms_by_ajax, name="validate_form"),
    path("unlock/<int:pk>", unlock, name="unlock")
]

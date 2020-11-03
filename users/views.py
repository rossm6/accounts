from accountancy.views import ajax_form_validator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import (LoginView, PasswordResetConfirmView,
                                       PasswordResetView)
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from users.forms import (SignInForm, SignUpForm, UserPasswordResetForm,
                         UserProfileForm, UserSetPasswordForm)


class SignUp(CreateView):
    model = User
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")


validate_forms_by_ajax = ajax_form_validator({
    "signup": SignUpForm
})


class SignIn(LoginView):
    form_class = SignInForm


class Profile(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "registration/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self):
        return self.request.user


class UserPasswordResetView(PasswordResetView):
    form_class = UserPasswordResetForm


class UserPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = UserSetPasswordForm

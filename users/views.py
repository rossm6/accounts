from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import (LoginView, PasswordResetConfirmView,
                                       PasswordResetView)
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from users.forms import (SignInForm, SignUpForm, UserPasswordResetForm,
                         UserProfileForm, UserSetPasswordForm)
from users.mixins import LockDuringEditMixin
from users.models import Lock


class SignUp(CreateView):
    model = User
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("dashboard:dashboard")


class SignIn(LoginView):
    form_class = SignInForm


class Profile(LoginRequiredMixin, LockDuringEditMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "registration/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, self.request.user)
        return response


class UserPasswordResetView(PasswordResetView):
    form_class = UserPasswordResetForm


class UserPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = UserSetPasswordForm


def unlock(request, pk):
    if request.method == "POST":
        lock = Lock.objects.filter(pk=pk).delete()
        return HttpResponse('')
    return HttpResponseNotAllowed(["POST"])

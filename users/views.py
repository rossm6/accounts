from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.shortcuts import render

from users.forms import SignUpForm

from accountancy.views import ajax_form_validator

class SignUp(CreateView):
    model = User
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")


validate_forms_by_ajax = ajax_form_validator({
    "signup": SignUpForm
})


def profile(request):
    return render(request, "registration/profile.html", {})
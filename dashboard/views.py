from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashBoard(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

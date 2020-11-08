from django.views.generic import TemplateView

class DashBoard(TemplateView):
    template_name = "dashboard/dashboard.html"
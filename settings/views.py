from accountancy.mixins import ResponsivePaginationMixin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.views.generic import DetailView, ListView, TemplateView


class SettingsView(TemplateView):
    template_name = "settings/settings.html"


class GroupsView(ResponsivePaginationMixin, ListView):
    paginate_by = 25
    model = Group
    template_name = "settings/group_list.html"


class GroupDetail(DetailView):
    model = Group
    template_name = "settings/detail.html"

class UsersView(ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"

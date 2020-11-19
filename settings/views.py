from accountancy.mixins import ResponsivePaginationMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.views.generic import DetailView, ListView, TemplateView


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = "settings/settings.html"


class GroupsView(LoginRequiredMixin, ResponsivePaginationMixin, ListView):
    paginate_by = 25
    model = Group
    template_name = "settings/group_list.html"


class GroupDetail(LoginRequiredMixin, DetailView):
    model = Group
    template_name = "settings/detail.html"


class UsersView(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"

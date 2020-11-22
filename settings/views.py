from accountancy.mixins import ResponsivePaginationMixin
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from settings.forms import UI_PERMISSIONS, GroupForm
from settings.helpers import PermissionUI


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = "settings/settings.html"


class GroupsView(LoginRequiredMixin, ResponsivePaginationMixin, ListView):
    paginate_by = 25
    model = Group
    template_name = "settings/group_list.html"


class GroupDetail(LoginRequiredMixin, DetailView):
    model = Group
    template_name = "settings/detail.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        group = self.object
        group_perms = group.permissions.all()
        perm_ui = PermissionUI(group_perms)
        for perm in UI_PERMISSIONS.all():
            perm_ui.add_to_group(perm)
        perm_table_rows = perm_ui.create_table_rows()
        context_data["perm_table_rows"] = perm_table_rows
        return context_data


class GroupUpdate(LoginRequiredMixin, UpdateView):
    model = Group
    template_name = "settings/edit.html"
    success_url = reverse_lazy("settings:groups")
    form_class = GroupForm


class UsersView(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"

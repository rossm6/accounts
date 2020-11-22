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


class GroupsList(LoginRequiredMixin, ResponsivePaginationMixin, ListView):
    paginate_by = 25
    model = Group
    template_name = "settings/group_list.html"


class GroupIndividualMixin:
    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["edit"] = self.edit
        return context_data


class ReadPermissionsMixin:
    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        perms = self.get_perms()
        perm_ui = PermissionUI(perms)
        for perm in UI_PERMISSIONS.all():
            perm_ui.add_to_group(perm)
        perm_table_rows = perm_ui.create_table_rows()
        context_data["perm_table_rows"] = perm_table_rows
        return context_data


class GroupDetail(
        LoginRequiredMixin,
        ReadPermissionsMixin,
        GroupIndividualMixin,
        DetailView):
    model = Group
    template_name = "settings/detail.html"
    edit = False

    def get_perms(self):
        return self.object.permissions.all()


class GroupUpdate(LoginRequiredMixin, GroupIndividualMixin, UpdateView):
    model = Group
    template_name = "settings/edit.html"
    success_url = reverse_lazy("settings:groups")
    form_class = GroupForm
    edit = True


class UsersList(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"


class UserDetail(
        LoginRequiredMixin,
        ReadPermissionsMixin,
        DetailView):
    model = User
    template_name = "settings/user_detail.html"
    edit = False

    def get_perms(self):
        return self.object.user_permissions.all()

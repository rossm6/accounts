from accountancy.mixins import ResponsivePaginationMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.views.generic import DetailView, ListView, TemplateView
from purchases.permissions import ModelPermissions

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
        perms = ModelPermissions.get_perms_for_users()
        forms = ModelPermissions.get_forms_for_perms(perms)
        perm_forms = {
            "Purchase Ledger": forms
        }
        context_data["perm_forms"] = perm_forms
        print(perm_forms)
        return context_data


class UsersView(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"

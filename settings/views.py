from accountancy.mixins import ResponsivePaginationMixin
from cashbook.permissions import CashBookPermissions
from contacts.permissions import ContactsPermissions
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from nominals.permissions import NominalsPermissions
from purchases.permissions import PurchasesPermissions
from sales.permissions import SalesPermissions
from vat.permissions import VatPermissions

MODULE_PERMISSIONS = (
    CashBookPermissions,
    ContactsPermissions,
    NominalsPermissions,
    PurchasesPermissions,
    SalesPermissions,
    VatPermissions
)


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
        module_perm_forms = {}
        group = self.object
        group_permissions = group.permissions.all()
        for module_perm_cls in MODULE_PERMISSIONS:
            module_perms = module_perm_cls.get_perms_for_users()
            module_perm_forms[module_perm_cls.module] = module_perm_cls.get_forms_for_perms(
                module_perms, group_permissions)
        context_data["module_perm_forms"] = module_perm_forms
        return context_data


class MultipleForms:
    def __init__(self, group, module_perm_forms):
        forms = []
        for module_name, sections in module_perm_forms.items():
            for section_name, perms in sections.items():
                for perm_thing, form in perms.items():
                    forms.append(form)
        self.forms = forms
        self.module_perm_forms = module_perm_forms
        self.group = group

    def is_valid(self):
        valid = True
        for form in self.forms:
            if not form.is_valid():
                valid = False
        return valid

    def save(self):
        total_perms = []  # list of perm objects
        for form in self.forms:
            perms = [perm for perm, enabled in form.cleaned_data.items()
                     if enabled]
            total_perms += [form.field_to_perm[perm] for perm in perms]
        self.group.permissions.clear()
        self.group.permissions.add(*total_perms)
        self.group.save()
        return self.group


class GroupUpdate(LoginRequiredMixin, UpdateView):
    model = Group
    template_name = "settings/detail.html"
    success_url = reverse_lazy("settings:groups")

    def get_module_perm_forms(self):
        kwargs = {}
        module_perm_forms = {}
        group = self.object
        group_permissions = group.permissions.all()
        for module_perm_cls in MODULE_PERMISSIONS:
            module_perms = module_perm_cls.get_perms_for_users()
            if self.request.method == "POST":
                kwargs["data"] = self.request.POST
            module_perm_forms[module_perm_cls.module] = module_perm_cls.get_forms_for_perms(
                module_perms, group_permissions, **kwargs)
        return module_perm_forms

    def get_form(self):
        module_perm_forms = self.get_module_perm_forms()
        return MultipleForms(self.object, module_perm_forms)

    def form_invalid(self, multiple_form_class_obj):
        return self.render_to_response(
            self.get_context_data(
                module_perm_forms=multiple_form_class_obj.module_perm_forms
            )
        )

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        if "module_perm_forms" not in kwargs:
            context_data["module_perm_forms"] = self.get_module_perm_forms()
        return context_data


class UsersView(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"

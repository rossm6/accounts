from itertools import chain

from accountancy.mixins import (ResponsivePaginationMixin,
                                SingleObjectAuditDetailViewMixin)
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models import prefetch_related_objects
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from settings.forms import UI_PERMISSIONS, GroupForm, UserForm
from settings.helpers import PermissionUI


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = "settings/settings.html"


class GroupsList(LoginRequiredMixin, ResponsivePaginationMixin, ListView):
    paginate_by = 25
    model = Group
    template_name = "settings/group_list.html"


class IndividualMixin:
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
        SingleObjectAuditDetailViewMixin,
        ReadPermissionsMixin,
        IndividualMixin,
        DetailView):
    model = Group
    template_name = "settings/detail.html"
    edit = False

    def get_perms(self):
        return self.object.permissions.all()


class GroupUpdate(
        LoginRequiredMixin,
        SingleObjectAuditDetailViewMixin,
        IndividualMixin,
        UpdateView):
    model = Group
    template_name = "settings/edit.html"
    success_url = reverse_lazy("settings:groups")
    form_class = GroupForm
    edit = True


class UsersList(LoginRequiredMixin, ListView):
    paginate_by = 25
    model = User
    template_name = "settings/users_list.html"


"""

    The permissions tab in the UI for the user detail and user edit shows BOTH
    the permissions of the groups the user belongs to and the permissions for that particular user.

    In edit mode the user only has the option to change the latter.

"""


class UserDetail(
        LoginRequiredMixin,
        SingleObjectAuditDetailViewMixin,
        ReadPermissionsMixin,
        DetailView):
    model = User
    template_name = "settings/user_detail.html"
    edit = False

    def get_perms(self):
        user = self.object
        user_perms = user.user_permissions.all()
        prefetch_related_objects([user], "groups__permissions__content_type")
        group_perms = [group.permissions.all() for group in user.groups.all()]
        group_perms = list(chain(*group_perms))
        if user_perms and group_perms:
            return list(set(chain(user_perms, group_perms)))
        if user_perms:
            return user_perms
        if group_perms:
            return group_perms


class UserEdit(
        LoginRequiredMixin,
        SingleObjectAuditDetailViewMixin,
        IndividualMixin,
        UpdateView):
    model = User
    form_class = UserForm
    template_name = "settings/user_edit.html"
    success_url = reverse_lazy("settings:users")
    edit = True

    # because 5 db hits are needed for POST
    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_form(self):
        form = self.form_class(**self.get_form_kwargs())
        user = self.object
        prefetch_related_objects([user], "groups__permissions__content_type")
        group_perms = [group.permissions.all()
                       for group in user.groups.all()]  # does hit db again
        group_perms = list(chain(*group_perms))  # does not hit db again
        group_perms = {perm.pk: perm for perm in group_perms}
        self.group_perms = group_perms
        form.fields["user_permissions"].widget.group_perms = group_perms
        return form

    def form_valid(self, form):
        groups = form.cleaned_data.get("groups")
        user_permissions = form.cleaned_data.get("user_permissions")
        # because the group permissions are included in the form i.e. checkboxes are ticked for
        # permissions which belong to only groups and not users, we need to discount all such permissions
        user_permissions = [
            perm for perm in user_permissions if perm.pk not in self.group_perms]
        form.instance.user_permissions.clear()  # hit db
        form.instance.user_permissions.add(*user_permissions)  # hit db
        form.instance.groups.clear()  # hit db
        form.instance.groups.add(*groups)  # hit db
        form.save()  # hit db
        return super().form_valid(form)

    def form_invalid(self, form):
        print(form.errors)
        return super().form_invalid(form)

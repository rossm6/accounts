from itertools import chain

from accountancy.mixins import (ResponsivePaginationMixin,
                                SingleObjectAuditDetailViewMixin)
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models import prefetch_related_objects
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DetailView, ListView,
                                  TemplateView, UpdateView)
from simple_history.utils import (bulk_create_with_history,
                                  bulk_update_with_history)

from settings.forms import (UI_PERMISSIONS, FinancialYearForm,
                            FinancialYearInlineFormSetCreate,
                            FinancialYearInlineFormSetEdit, GroupForm,
                            PeriodForm, UserForm)
from settings.helpers import PermissionUI
from settings.models import FinancialYear, Period


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
        return super().form_invalid(form)


class FinancialYearList(ListView):
    model = FinancialYear
    template_name = "settings/fy_list.html"


class FinancialYearCreateEditMixin:
    model = FinancialYear
    template_name = 'settings/fy_create.html'
    form_class = FinancialYearForm
    success_url = reverse_lazy("settings:index")

    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


def change_fy():
    """
    This should work recursively.  These testing.
    """
    pass

def extend_fy(all_periods, fy_extended, number_of_periods):
    pass

def distend_fy(all_periods, fy_distended, number_of_periods):
    pass


class FinancialYearCreate(FinancialYearCreateEditMixin, CreateView):

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        if self.request.POST:
            context_data["periods"] = FinancialYearInlineFormSetCreate(
                self.request.POST, prefix="period")
        else:
            context_data["periods"] = FinancialYearInlineFormSetCreate(
                prefix="period")
        return context_data

    def form_valid(self, form):
        context_data = self.get_context_data()
        periods = context_data["periods"]
        if periods.is_valid():
            fy = form.save()
            self.object = fy
            periods.save(commit=False)
            i = 1
            for period in periods:
                period.instance.period = f"{fy.financial_year}{str(i).rjust(2, '0')}"
                period.instance.fy = fy
                i = i + 1
            bulk_create_with_history(
                [period.instance for period in periods],
                Period
            )
            return HttpResponseRedirect(self.get_success_url())
        return self.render_to_response(context_data)


class FinancialYearDetail(DetailView):
    model = FinancialYear
    template_name = "settings/fy_detail.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        periods = self.object.periods.all()
        context_data["periods"] = periods
        return context_data


class FinancialYearEdit(FinancialYearCreateEditMixin, UpdateView):

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        if self.request.POST:
            context_data["periods"] = FinancialYearInlineFormSetEdit(
                self.request.POST, prefix="period", instance=self.object)
        else:
            context_data["periods"] = FinancialYearInlineFormSetEdit(
                prefix="period", instance=self.object)
        return context_data

    def form_valid(self, form):
        context_data = self.get_context_data()
        periods = context_data["periods"]
        if periods.is_valid():
            fy = form.save()
            self.object = fy
            periods.save(commit=False)
            i = 1
            for period in periods:
                period.instance.period = f"{fy.financial_year}{str(i).rjust(2, '0')}"
                period.instance.fy = fy
                i = i + 1
            bulk_create_with_history(
                [period for period in periods.new_objects],
                Period,
            )
            to_update = [
                period.instance for period in periods if period.instance not in periods.new_objects]
            bulk_update_with_history(
                [period for period in to_update],
                Period,
                ["month_end", "period", "fy"]
            )
            return HttpResponseRedirect(self.get_success_url())
        return self.render_to_response(context_data)

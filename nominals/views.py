import collections
from json import loads

from accountancy.forms import BaseVoidTransactionForm
from accountancy.helpers import FY, Period
from accountancy.mixins import SingleObjectAuditDetailViewMixin
from accountancy.views import (BaseCreateTransaction, BaseEditTransaction,
                               BaseViewTransaction, BaseVoidTransaction,
                               CashBookAndNominalTransList)
from crispy_forms.utils import render_crispy_form
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from mptt.utils import get_cached_trees
from users.mixins import LockDuringEditMixin, LockTransactionDuringEditMixin
from vat.forms import VatForm
from vat.models import VatTransaction

from nominals.forms import NominalTransactionSearchForm, TrialBalanceForm

from .forms import NominalForm, NominalHeaderForm, NominalLineForm, enter_lines
from .models import Nominal, NominalHeader, NominalLine, NominalTransaction


class CreateTransaction(LoginRequiredMixin, BaseCreateTransaction):
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "can_order": False
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat")
    }
    template_name = "nominals/create.html"
    success_url = reverse_lazy("nominals:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    vat_transaction_model = VatTransaction
    module = "NL"
    default_type = "nj"


class EditTransaction(LoginRequiredMixin, LockTransactionDuringEditMixin, BaseEditTransaction):
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header"
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "can_order": False
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat")
    }
    template_name = "nominals/edit.html"
    success_url = reverse_lazy("nominals:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    vat_transaction_model = VatTransaction
    module = "NL"


class ViewTransaction(LoginRequiredMixin, BaseViewTransaction):
    model = NominalHeader
    line_model = NominalLine
    module = 'NL'
    void_form_action = "nominals:void"
    void_form = BaseVoidTransactionForm
    template_name = "nominals/view.html"
    edit_view_name = "nominals:edit"


class TransactionEnquiry(LoginRequiredMixin, CashBookAndNominalTransList):
    model = NominalTransaction
    # ORDER OF FIELDS HERE IS IMPORTANT FOR GROUPING THE SQL QUERY
    # ATM -
    # GROUP BY MODULE, HEADER, NOMINAL__NAME, PERIOD
    fields = [
        ("module", "Module"),
        ("header", "Internal Ref"),
        ("ref", "Ref"),
        ("nominal__name", "Nominal"),
        ("period__fy_and_period", "Period"),
        ("date", "Date"),
        ("total", "Total"),
    ]
    form_field_to_searchable_model_attr = {
        "reference": "ref"
    }
    filter_form_class = NominalTransactionSearchForm
    template_name = "nominals/transactions.html"
    row_identifier = "header"
    column_transformers = {
        "period__fy_and_period": lambda p: p[4:] + " " + p[:4],
    }

    def load_page(self):
        context_data = super().load_page()
        context_data["nominal_form"] = NominalForm(action=reverse_lazy(
            "nominals:nominal_create"), prefix="nominal")
        return context_data

    def get_row_href(self, obj):
        module = obj["module"]
        header = obj["header"]
        modules = settings.ACCOUNTANCY_MODULES
        module_name = modules[module]
        return reverse_lazy(module_name + ":view", kwargs={"pk": header})

    def apply_advanced_search(self, queryset, cleaned_data):
        queryset = super().apply_advanced_search(queryset, cleaned_data)
        if nominal := cleaned_data.get("nominal"):
            queryset = queryset.filter(nominal=nominal)
        return queryset

    # this should belong to the parent class
    def get_queryset(self, **kwargs):
        return (
            NominalTransaction.objects
            .select_related('nominal__name')
            .select_related('period__fy_and_period')
            .all()
            .values(
                *[field[0] for field in self.fields[:-1]]
            )
            .annotate(total=Sum("value"))
            .order_by(*self.order_by())
        )


class VoidTransaction(LoginRequiredMixin, LockTransactionDuringEditMixin, BaseVoidTransaction):
    header_model = NominalHeader
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("nominals:transaction_enquiry")
    module = 'NL'
    vat_transaction_model = VatTransaction


class TrialBalance(LoginRequiredMixin, ListView):
    template_name = "nominals/trial_balance.html"
    columns = [
        'Nominal',
        'parent',
        'grand_parent',
        'Debit',
        'Credit',
        'YTD Debit',
        'YTD Credit'
    ]

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = {}
        context["columns"] = columns = [col for col in self.columns]
        if self.request.GET:
            context["form"] = form = TrialBalanceForm(
                data=self.request.GET,
                initial={
                    "from_period": "202001",
                    "to_period": "202007"
                }
            )
            if form.is_valid():
                from_period = form.cleaned_data.get("from_period")
                to_period = form.cleaned_data.get("to_period")
            else:
                self.object_list = context["report"] = []  # show empty table
                return context
        else:
            from_period = "202001"
            to_period = "202007"
            context["form"] = TrialBalanceForm(
                initial={
                    "from_period": from_period,
                    "to_period": to_period
                }
            )
        nominals = Nominal.objects.all().prefetch_related("children")
        # hits the DB but will cache result
        root_nominals = get_cached_trees(nominals)
        # this means we can use get_ancestors() on the nodes now without hitting the DB again
        nominal_map = {nominal.pk: nominal for nominal in nominals}
        nominal_totals_for_period_range = (
            NominalTransaction.objects
            .values("nominal")
            .annotate(total=Sum("value"))
            .filter(period__gte=from_period)
            .filter(period__lte=to_period)
        )
        # get the start of the financial year the to_period is in
        from_period = FY(to_period).start()
        nominal_ytd_totals = (
            NominalTransaction.objects
            .values("nominal")
            .annotate(total=Sum("value"))
            .filter(period__gte=from_period)
            .filter(period__lte=to_period)
        )
        report = []
        debit_total = 0
        credit_total = 0
        ytd_debit_total = 0
        ytd_credit_total = 0
        for nominal_total in nominal_totals_for_period_range:
            nominal_pk = nominal_total["nominal"]
            total = nominal_total["total"]
            if total > 0:
                debit_total += total
            else:
                credit_total += total
            parents = [
                parent.name for parent in nominal_map[nominal_pk].get_ancestors()]
            for ytd in nominal_ytd_totals:
                if ytd["nominal"] == nominal_pk:
                    ytd = ytd["total"]
                    if ytd > 0:
                        ytd_debit_total += ytd
                    else:
                        ytd_credit_total += ytd
                    break
            nominal_report = {
                "nominal": nominal_map[nominal_pk].name,
                "total": total,
                "parents": parents,
                "ytd": ytd
            }
            report.append(nominal_report)
        context["debit_total"] = debit_total
        context["credit_total"] = credit_total
        context["ytd_debit_total"] = ytd_debit_total
        context["ytd_credit_total"] = ytd_credit_total
        self.object_list = context["report"] = report
        return context


class LoadNominal(LoginRequiredMixin, ListView):
    paginate_by = 50
    model = Nominal

    def get_model(self):
        return self.model

    def get_queryset(self):
        if q := self.request.GET.get('q'):
            return (
                self.get_model().objects.annotate(
                    similarity=TrigramSimilarity('name', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return self.get_model().objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        # we need to know the root nodes for each node which has no children
        nodes = context["page_obj"].object_list
        selectable_nodes = [node for node in nodes if node.is_leaf_node()]
        all_nominals = Nominal.objects.all().prefetch_related("children")  # whole set
        # hits the DB but will cache result
        # root nodes are the groups for the select menu
        root_nominals = get_cached_trees(all_nominals)
        root_nominals.sort(key=lambda n: n.pk)
        options = [
            {
                "group": node.get_root(),
                "option": node,
                "group_order": root_nominals.index(node.get_root())
            }
            for node in selectable_nodes
        ]
        context["options"] = options
        return context

    def render_to_response(self, context, **response_kwargs):
        options = []
        for option in context["options"]:
            o = {
                'group_value': option["group"].pk,
                'group_label': str(option["group"]),
                'opt_value': option["option"].pk,
                'opt_label': str(option["option"]),
                'group_order': option["group_order"]
            }
            options.append(o)
        options.sort(key=lambda o: o["group_order"])
        data = {"data": options}
        return JsonResponse(data)


class NominalCreate(LoginRequiredMixin, CreateView):
    model = Nominal
    form_class = NominalForm
    success_url = reverse_lazy("nominals:nominals_list")
    template_name = "nominals/nominal_create_and_edit.html"
    prefix = "nominal"

    def form_valid(self, form):
        redirect_response = super().form_valid(form)
        if self.request.is_ajax():
            data = {}
            new_nominal = self.object
            group = new_nominal.get_root()  # i.e. asset, liabilities etc
            data["new_object"] = {
                "opt_value": new_nominal.pk,
                "opt_label": str(new_nominal),
                "group_value": group.pk,
                "group_label": str(group)
            }
            data["success"] = True
            return JsonResponse(data=data)
        return redirect_response

    def render_to_response(self, context, **response_kwargs):
        # form is not valid
        if self.request.is_ajax():
            ctx = {}
            ctx.update(csrf(self.request))
            form = context["form"]
            form_html = render_crispy_form(form, context=ctx)
            data = {
                "form_html": form_html,
                "success": False
            }
            return JsonResponse(data=data)
        return super().render_to_response(context, **response_kwargs)


class NominalList(LoginRequiredMixin, ListView):
    model = Nominal
    template_name = "nominals/nominal_list.html"
    context_object_name = "nominals"


class NominalDetail(LoginRequiredMixin, SingleObjectAuditDetailViewMixin, DetailView):
    model = Nominal
    template_name = "nominals/nominal_detail.html"


class NominalEdit(LoginRequiredMixin, LockDuringEditMixin, UpdateView):
    model = Nominal
    form_class = NominalForm
    template_name = "nominals/nominal_create_and_edit.html"
    success_url = reverse_lazy("nominals:nominals_list")
    prefix = "nominal"

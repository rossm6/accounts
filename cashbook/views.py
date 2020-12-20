from accountancy.forms import BaseVoidTransactionForm
from accountancy.mixins import SingleObjectAuditDetailViewMixin
from accountancy.views import (BaseViewTransaction, BaseVoidTransaction,
                               CashBookAndNominalTransList,
                               CreateCashBookTransaction,
                               DeleteCashBookTransMixin,
                               EditCashBookTransaction,
                               NominalTransactionsMixin)
from django.conf import settings
from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        PermissionRequiredMixin)
from django.db.models import Sum
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from users.mixins import LockDuringEditMixin, LockTransactionDuringEditMixin
from vat.forms import VatForm
from vat.models import VatTransaction

from cashbook.forms import CashBookForm, CashBookTransactionSearchForm
from cashbook.models import CashBook

from .forms import CashBookHeaderForm, CashBookLineForm, enter_lines
from .models import CashBookHeader, CashBookLine, CashBookTransaction
from accountancy.contrib.mixins import TransactionPermissionMixin
from controls.mixins import QueuePostsMixin


class CreateTransaction(
        LoginRequiredMixin,
        TransactionPermissionMixin,
        QueuePostsMixin,
        CreateCashBookTransaction):
    header = {
        "model": CashBookHeader,
        "form": CashBookHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": CashBookLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat"),
    }
    template_name = "cashbook/create.html"
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction
    module = "CB"
    default_type = "cp"


class EditTransaction(
        LoginRequiredMixin,
        TransactionPermissionMixin,
        QueuePostsMixin,
        LockTransactionDuringEditMixin,
        EditCashBookTransaction):
    header = {
        "model": CashBookHeader,
        "form": CashBookHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": CashBookLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat"),
    }
    template_name = "cashbook/edit.html"
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction
    module = "CB"


class ViewTransaction(
        LoginRequiredMixin,
        TransactionPermissionMixin,
        NominalTransactionsMixin,
        BaseViewTransaction):
    model = CashBookHeader
    line_model = CashBookLine
    nominal_transaction_model = NominalTransaction
    module = 'CB'
    void_form_action = "cashbook:void"
    void_form = BaseVoidTransactionForm
    template_name = "cashbook/view.html"
    edit_view_name = "cashbook:edit"


class VoidTransaction(
        LoginRequiredMixin,
        TransactionPermissionMixin,
        QueuePostsMixin,
        LockTransactionDuringEditMixin,
        DeleteCashBookTransMixin,
        BaseVoidTransaction):
    header_model = CashBookHeader
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    module = 'CB'
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction


class TransactionEnquiry(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CashBookAndNominalTransList
):
    model = CashBookTransaction
    fields = [
        ("module", "Module"),
        ("header", "Internal Ref"),
        ("ref", "Ref"),
        ("cash_book__name", "Cash Book"),
        ("period__fy_and_period", "Period"),
        ("date", "Date"),
        ("total", "Total"),
    ]
    form_field_to_searchable_model_attr = {
        "reference": "ref"
    }
    filter_form_class = CashBookTransactionSearchForm
    template_name = "cashbook/transactions.html"
    row_identifier = "header"
    column_transformers = {
        "period__fy_and_period": lambda p: p[4:] + " " + p[:4],
        "date": lambda d: d.strftime('%d %b %Y'),
    }
    permission_required = 'cashbook.view_transactions_enquiry'

    def load_page(self):
        context_data = super().load_page()
        context_data["cashbook_form"] = CashBookForm(action=reverse_lazy(
            "cashbook:cashbook_create"), prefix="cashbook")
        context_data["nominal_form"] = NominalForm(action=reverse_lazy(
            "nominals:nominal_create"), prefix="nominal")
        context_data["form"] = self.get_filter_form()
        return context_data

    def get_row_href(self, obj):
        module = obj["module"]
        header = obj["header"]
        modules = settings.ACCOUNTANCY_MODULES
        module_name = modules[module]
        return reverse_lazy(module_name + ":view", kwargs={"pk": header})

    def apply_advanced_search(self, queryset, cleaned_data):
        queryset = super().apply_advanced_search(queryset, cleaned_data)
        if cashbook := cleaned_data.get("cashbook"):
            queryset = queryset.filter(cashbook=cashbook)
        return queryset

    def get_queryset(self, **kwargs):
        return (
            CashBookTransaction.objects
            .select_related('cash_book__name')
            .select_related('period__fy_and_period')
            .all()
            .values(
                *[field[0] for field in self.fields[:-1]]
            )
            .annotate(total=Sum("value"))
            .order_by(*self.order_by())
        )


class CreateAndEditMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["nominal_form"] = NominalForm(action=reverse_lazy(
            "nominals:nominal_create"), prefix="nominal")
        return context


class CashBookCreate(
        LoginRequiredMixin,
        PermissionRequiredMixin,
        CreateAndEditMixin,
        CreateView):
    model = CashBook
    form_class = CashBookForm
    # till we have a cash book list
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    template_name = "cashbook/cashbook_create_and_edit.html"
    prefix = "cashbook"
    permission_required = 'cashbook.add_cashbook'

    def form_valid(self, form):
        redirect_response = super().form_valid(form)
        if self.request.is_ajax():
            data = {}
            new_cashbook = self.object
            data["new_object"] = {
                "id": new_cashbook.pk,
                "name": new_cashbook.name
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


class CashBookList(LoginRequiredMixin, ListView):
    model = CashBook
    template_name = "cashbook/cashbook_list.html"
    context_object_name = "cashbooks"


class CashBookDetail(
        LoginRequiredMixin,
        PermissionRequiredMixin,
        SingleObjectAuditDetailViewMixin,
        DetailView):
    model = CashBook
    template_name = "cashbook/cashbook_detail.html"
    permission_required = 'cashbook.view_cashbook'


class CashBookEdit(
        LoginRequiredMixin,
        PermissionRequiredMixin,
        LockDuringEditMixin,
        CreateAndEditMixin,
        UpdateView):
    model = CashBook
    form_class = CashBookForm
    template_name = "cashbook/cashbook_create_and_edit.html"
    success_url = reverse_lazy("cashbook:cashbook_list")
    prefix = "cashbook"
    permission_required = 'cashbook.change_cashbook'

from accountancy.forms import BaseVoidTransactionForm
from accountancy.views import (BaseVoidTransaction,
                               CreatePurchaseOrSalesTransaction,
                               DeleteCashBookTransMixin,
                               EditPurchaseOrSalesTransaction,
                               LoadMatchingTransactions,
                               SaleAndPurchaseViewTransaction,
                               SalesAndPurchasesTransList)
from cashbook.models import CashBookTransaction
from contacts.forms import ModalContactForm
from contacts.views import LoadContacts
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from purchases.views import AgeCreditorsReport
from users.mixins import LockTransactionDuringEditMixin
from vat.forms import VatForm
from vat.models import VatTransaction

from sales.forms import (DebtorsForm, SaleHeaderForm, SaleLineForm,
                         SaleTransactionSearchForm, enter_lines, match)
from sales.models import Customer, SaleHeader, SaleLine, SaleMatching

SALES_CONTROL_ACCOUNT = "Sales Ledger Control"


class CustomerMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["loading_matching_transactions_url"] = reverse_lazy(
            "sales:load_matching_transactions")
        return context

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        kwargs["contact_model_name"] = "customer"
        return kwargs


class CreateTransaction(LoginRequiredMixin, CustomerMixin, CreatePurchaseOrSalesTransaction):
    header = {
        "model": SaleHeader,
        "form": SaleHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": SaleLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    match = {
        "model": SaleMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalContactForm(action=reverse_lazy("contacts:create"), prefix="contact", initial={"customer": True}),
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat")
    }
    template_name = "sales/create.html"
    success_url = reverse_lazy("sales:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "SL"
    control_nominal_name = SALES_CONTROL_ACCOUNT
    cash_book_transaction_model = CashBookTransaction
    default_type = "si"
    vat_transaction_model = VatTransaction


class EditTransaction(
        LoginRequiredMixin,
        LockTransactionDuringEditMixin,
        CustomerMixin,
        EditPurchaseOrSalesTransaction):
    header = {
        "model": SaleHeader,
        "form": SaleHeaderForm,
        "prefix": "header",
    }
    line = {
        "model": SaleLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    match = {
        "model": SaleMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalContactForm(action=reverse_lazy("contacts:create"), prefix="contact"),
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat")
    }
    template_name = "sales/edit.html"
    success_url = reverse_lazy("sales:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "SL"
    control_nominal_name = SALES_CONTROL_ACCOUNT
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction


class ViewTransaction(LoginRequiredMixin, SaleAndPurchaseViewTransaction):
    model = SaleHeader
    line_model = SaleLine
    match_model = SaleMatching
    nominal_transaction_model = NominalTransaction
    module = 'SL'
    void_form_action = "sales:void"
    void_form = BaseVoidTransactionForm
    template_name = "sales/view.html"
    edit_view_name = "sales:edit"


class VoidTransaction(LoginRequiredMixin, LockTransactionDuringEditMixin, DeleteCashBookTransMixin, BaseVoidTransaction):
    header_model = SaleHeader
    matching_model = SaleMatching
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("sales:transaction_enquiry")
    module = 'SL'
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction


class LoadSaleMatchingTransactions(LoginRequiredMixin, LoadMatchingTransactions):
    model = SaleHeader
    match_model = SaleMatching
    contact_name = "customer"


class LoadCustomers(LoginRequiredMixin, LoadContacts):
    model = Customer

    def get_queryset(self):
        q = super().get_queryset()
        return q.filter(customer=True)


class TransactionEnquiry(LoginRequiredMixin, SalesAndPurchasesTransList):
    model = SaleHeader
    fields = [
        ("customer__name", "Customer"),
        ("ref", "Reference"),
        ("period__fy_and_period", "Period"),
        ("date", "Date"),
        ("due_date", "Due Date"),
        ("total", "Total"),
        ("paid", "Paid"),
        ("due", "Due"),
    ]
    form_field_to_searchable_model_attr = {
        "reference": "ref"
    }
    column_transformers = {
        "period__fy_and_period": lambda p: p[4:] + " " + p[:4],
        "date": lambda d: d.strftime('%d %b %Y'),
        # payment trans do not have due dates
        "due_date": lambda d: d.strftime('%d %b %Y') if d else ""
    }
    filter_form_class = SaleTransactionSearchForm
    contact_name = "customer"
    template_name = "sales/transactions.html"

    def load_page(self):
        context_data = super().load_page()
        context_data["contact_form"] = ModalContactForm(
            action=reverse_lazy("contacts:create"), prefix="contact")
        return context_data

    def get_row_href(self, obj):
        pk = obj["id"]
        return reverse_lazy("sales:view", kwargs={"pk": pk})

    def get_queryset(self, **kwargs):
        return (
            self.get_querysets(**kwargs)
            .select_related('customer__name')
            .select_related('period__fy_and_period')
            .all()
            .values(
                'id',
                *[field[0] for field in self.fields]
            )
            .order_by(*self.order_by())
        )

    def apply_advanced_search(self, queryset, cleaned_data):
        queryset = super().apply_advanced_search(queryset, cleaned_data)
        if customer := cleaned_data.get("customer"):
            queryset = queryset.filter(customer=customer)
        return queryset

    def get_querysets(self, **kwargs):
        group = self.request.GET.get("group", 'a')
        # add querysets to the instance
        # in context_data get the summed value for each
        self.all_queryset = SaleHeader.objects.all()
        self.awaiting_payment_queryset = SaleHeader.objects.exclude(due=0)
        self.overdue_queryset = SaleHeader.objects.exclude(
            due=0).filter(due_date__lt=timezone.now())
        self.paid_queryset = SaleHeader.objects.filter(due=0)
        if group == "a":
            return self.all_queryset
        elif group == "ap":
            return self.awaiting_payment_queryset
        elif group == "o":
            return self.overdue_queryset
        elif group == "p":
            return self.paid_queryset


class AgeDebtorsReport(AgeCreditorsReport):
    model = SaleHeader
    match_model = SaleMatching
    filter_form_class = DebtorsForm
    contact_range_field_names = ['from_customer', 'to_customer']
    contact_field_name = "customer"

from django.urls import reverse_lazy
from django.utils import timezone

from accountancy.forms import BaseVoidTransactionForm
from accountancy.views import (AgeMatchingReportMixin, BaseVoidTransaction,
                               CreatePurchaseOrSalesTransaction,
                               DeleteCashBookTransMixin,
                               EditPurchaseOrSalesTransaction, LoadContacts,
                               LoadMatchingTransactions,
                               SaleAndPurchaseViewTransaction,
                               SalesAndPurchasesTransList)
from cashbook.models import CashBookTransaction
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from sales.forms import SaleTransactionSearchForm
from vat.forms import VatForm

from .forms import (DebtorForm, ModalCustomerForm, SaleHeaderForm,
                    SaleLineForm, enter_lines, match)
from .models import Customer, SaleHeader, SaleLine, SaleMatching

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


class CreateTransaction(CustomerMixin, CreatePurchaseOrSalesTransaction):
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
        "contact_form": ModalCustomerForm(action=reverse_lazy("contacts:create_customer"), prefix="customer"),
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


class EditTransaction(CustomerMixin, EditPurchaseOrSalesTransaction):
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
        "contact_form": ModalCustomerForm(action=reverse_lazy("contacts:create_customer"), prefix="customer"),
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


class ViewTransaction(SaleAndPurchaseViewTransaction):
    model = SaleHeader
    line_model = SaleLine
    match_model = SaleMatching
    nominal_transaction_model = NominalTransaction
    module = 'SL'
    void_form_action = reverse_lazy("sales:void")
    void_form = BaseVoidTransactionForm
    template_name = "sales/view.html"
    edit_view_name = "sales:edit"

class VoidTransaction(DeleteCashBookTransMixin, BaseVoidTransaction):
    header_model = SaleHeader
    matching_model = SaleMatching
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("sales:transaction_enquiry")
    module = 'SL'
    cash_book_transaction_model = CashBookTransaction


class LoadSaleMatchingTransactions(LoadMatchingTransactions):
    header_model = SaleHeader
    matching_model = SaleMatching
    contact_name = "customer"


class LoadCustomers(LoadContacts):
    model = Customer


class TransactionEnquiry(SalesAndPurchasesTransList):
    model = SaleHeader
    fields = [
        ("customer__name", "Customer"),
        ("ref", "Reference"),
        ("period", "Period"),
        ("date", "Date"),
        ("due_date", "Due Date"),
        ("total", "Total"),
        ("paid", "Paid"),
        ("due", "Due"),
    ]
    form_field_to_searchable_model_field = {
        "reference": "ref"
    }
    datetime_fields = ["date", "due_date"]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = SaleTransactionSearchForm
    contact_name = "customer"
    template_name = "sales/transactions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contact_form"] = ModalCustomerForm(action=reverse_lazy("contacts:create_customer"), prefix="customer")
        return context

    def get_transaction_url(self, **kwargs):
        row = kwargs.pop("row")
        pk = row["id"]
        return reverse_lazy("sales:view", kwargs={"pk": pk})

    def get_queryset(self):
        return (
            self.get_querysets()
            .select_related('customer__name')
            .all()
            .values(
                'id',
                *[field[0] for field in self.fields]
            )
            .order_by(*self.order_by())
        )

    def apply_advanced_search(self, cleaned_data):
        queryset = super().apply_advanced_search(cleaned_data)
        if customer := cleaned_data.get("customer"):
            queryset = queryset.filter(customer=customer)
        return queryset

    def get_querysets(self):
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


class AgeDebtorsReport(AgeMatchingReportMixin):
    model = SaleHeader
    matching_model = SaleMatching
    filter_form = DebtorForm
    form_template = "accountancy/aged_matching_report_form.html"
    template_name = "accountancy/aged_matching_report.html"
    contact_range_field_names = ['from_customer', 'to_customer']
    contact_field_name = "customer"

from decimal import Decimal
from functools import reduce
from itertools import chain

from accountancy.forms import BaseVoidTransactionForm
from accountancy.helpers import AuditTransaction
from accountancy.views import (AgeMatchingReportMixin, BaseVoidTransaction,
                               CreatePurchaseOrSalesTransaction,
                               DeleteCashBookTransMixin,
                               EditPurchaseOrSalesTransaction,
                               JQueryDataTableMixin, LoadMatchingTransactions,
                               SaleAndPurchaseViewTransaction,
                               SalesAndPurchasesTransList)
from cashbook.models import CashBookTransaction
from contacts.forms import ModalContactForm
from contacts.views import LoadContacts
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, Sum
from django.http import (Http404, HttpResponse, HttpResponseBadRequest,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from querystring_parser import parser
from vat.forms import VatForm
from vat.models import Vat, VatTransaction

from purchases.forms import (CreditorsForm, PurchaseHeaderForm,
                             PurchaseLineForm, PurchaseTransactionSearchForm,
                             enter_lines, match)
from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)


class SupplierMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["loading_matching_transactions_url"] = reverse_lazy(
            "purchases:load_matching_transactions")
        return context

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        kwargs["contact_model_name"] = "supplier"
        return kwargs


class CreateTransaction(LoginRequiredMixin, SupplierMixin, CreatePurchaseOrSalesTransaction):
    header = {
        "model": PurchaseHeader,
        "form": PurchaseHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": PurchaseLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalContactForm(action=reverse_lazy("contacts:create"), prefix="contact", initial={"supplier": True}),
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat"),
    }
    template_name = "purchases/create.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    vat_transaction_model = VatTransaction
    module = "PL"
    control_nominal_name = "Purchase Ledger Control"
    cash_book_transaction_model = CashBookTransaction
    default_type = "pi"


class EditTransaction(LoginRequiredMixin, SupplierMixin, EditPurchaseOrSalesTransaction):
    header = {
        "model": PurchaseHeader,
        "form": PurchaseHeaderForm,
        "prefix": "header",
    }
    line = {
        "model": PurchaseLine,
        "formset": enter_lines,
        "prefix": "line",
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalContactForm(action=reverse_lazy("contacts:create"), prefix="contact"),
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat"),
    }
    template_name = "purchases/edit.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "PL"
    control_nominal_name = "Purchase Ledger Control"
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction

class ViewTransaction(LoginRequiredMixin, SaleAndPurchaseViewTransaction):
    model = PurchaseHeader
    line_model = PurchaseLine
    match_model = PurchaseMatching
    nominal_transaction_model = NominalTransaction
    module = 'PL'
    void_form_action = reverse_lazy("purchases:void")
    void_form = BaseVoidTransactionForm
    template_name = "purchases/view.html"
    edit_view_name = "purchases:edit"

class VoidTransaction(LoginRequiredMixin, DeleteCashBookTransMixin, BaseVoidTransaction):
    header_model = PurchaseHeader
    matching_model = PurchaseMatching
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("purchases:transaction_enquiry")
    module = 'PL'
    cash_book_transaction_model = CashBookTransaction
    vat_transaction_model = VatTransaction


class LoadPurchaseMatchingTransactions(LoginRequiredMixin, LoadMatchingTransactions):
    model = PurchaseHeader
    matching_model = PurchaseMatching
    contact_name = "supplier"


class LoadSuppliers(LoginRequiredMixin, LoadContacts):
    model = Supplier

    def get_queryset(self):
        q = super().get_queryset()
        return q.filter(supplier=True)


class TransactionEnquiry(LoginRequiredMixin, SalesAndPurchasesTransList):
    model = PurchaseHeader
    fields = [
        ("supplier__name", "Supplier"),
        ("ref", "Reference"),
        ("period", "Period"),
        ("date", "Date"),
        ("due_date", "Due Date"),
        ("total", "Total"),
        ("paid", "Paid"),
        ("due", "Due"),
    ]
    # perhaps we ought to just rename the field
    # also consider adding resizable columns
    form_field_to_searchable_model_attr = {
        "reference": "ref"
    }
    column_transformers = {
        "date": lambda d: d.strftime('%d %b %Y'),
        "due_date": lambda d: d.strftime('%d %b %Y')
    }
    filter_form_class = PurchaseTransactionSearchForm
    contact_name = "supplier"
    template_name = "purchases/transactions.html"

    def load_page(self):
        context_data = super().load_page()
        context_data["contact_form"] = ModalContactForm(
            action=reverse_lazy("contacts:create"), prefix="contact")
        return context_data

    def get_row_href(self, obj):
        pk = obj["id"]
        return reverse_lazy("purchases:view", kwargs={"pk": pk})

    def get_queryset(self):
        return (
            self.get_querysets()
            .select_related('supplier__name')
            .all()
            .values(
                'id',
                *[field[0] for field in self.fields]
            )
            # unneccessary because parent class does this
            .order_by(*self.order_by())
        )

    def apply_advanced_search(self, queryset, cleaned_data):
        queryset = super().apply_advanced_search(queryset, cleaned_data)
        if supplier := cleaned_data.get("supplier"):
            queryset = queryset.filter(supplier=supplier)
        return queryset

    def get_querysets(self):
        group = self.request.GET.get("group", 'a')
        # add querysets to the instance
        # in context_data get the summed value for each
        self.all_queryset = PurchaseHeader.objects.all()
        self.awaiting_payment_queryset = PurchaseHeader.objects.exclude(due=0)
        self.overdue_queryset = PurchaseHeader.objects.exclude(
            due=0).filter(due_date__lt=timezone.now())
        self.paid_queryset = PurchaseHeader.objects.filter(due=0)
        if group == "a":
            return self.all_queryset
        elif group == "ap":
            return self.awaiting_payment_queryset
        elif group == "o":
            return self.overdue_queryset
        elif group == "p":
            return self.paid_queryset


class AgeCreditorsReport(LoginRequiredMixin, AgeMatchingReportMixin):
    model = PurchaseHeader
    match_model = PurchaseMatching
    filter_form_class = CreditorsForm
    form_template = "accountancy/aged_matching_report_form.html"
    template_name = "accountancy/aged_matching_report.html"
    contact_range_field_names = ['from_supplier', 'to_supplier']
    contact_field_name = "supplier"

    def load_page(self, **kwargs):
        context = super().load_page(**kwargs)
        context["contact_form"] = ModalContactForm(
            action=reverse_lazy("contacts:create"), prefix="contact")
        return context

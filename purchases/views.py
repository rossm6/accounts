from decimal import Decimal
from functools import reduce
from itertools import chain

from django.contrib import messages
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, Sum
from django.http import (Http404, HttpResponse, HttpResponseBadRequest,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView
from querystring_parser import parser

from accountancy.exceptions import FormNotValid
from accountancy.forms import (BaseVoidTransactionForm,
                               SalesAndPurchaseTransactionSearchForm)
from accountancy.helpers import AuditTransaction
from accountancy.views import (AgeMatchingReportMixin, BaseViewTransaction,
                               BaseVoidTransaction,
                               CreatePurchaseOrSalesTransaction,
                               DeleteCashBookTransMixin,
                               EditPurchaseOrSalesTransaction, LoadContacts,
                               LoadMatchingTransactions,
                               SalesAndPurchasesTransList,
                               ViewTransactionOnLedgerOtherThanNominal,
                               jQueryDataTable)
from cashbook.models import CashBookTransaction
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from purchases.forms import ModalSupplierForm
from vat.forms import VatForm
from vat.models import Vat

from .forms import (CreditorForm, PurchaseHeaderForm, PurchaseLineForm,
                    ReadOnlyPurchaseHeaderForm, enter_lines, match,
                    read_only_lines, read_only_match)
from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


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


class CreateTransaction(SupplierMixin, CreatePurchaseOrSalesTransaction):
    header = {
        "model": PurchaseHeader,
        "form": PurchaseHeaderForm,
        "prefix": "header",
        "override_choices": ["supplier"],
        "initial": {"total": 0},

    }
    line = {
        "model": PurchaseLine,
        "formset": enter_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalSupplierForm(action=reverse_lazy("contacts:create_supplier"), prefix="supplier"),
        "nominal_form": NominalForm(action=reverse_lazy("nominals:nominal_create"), prefix="nominal"),
        "vat_form": VatForm(action=reverse_lazy("vat:vat_create"), prefix="vat"),
    }
    template_name = "purchases/create.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "PL"
    control_nominal_name = "Purchase Ledger Control"
    cash_book_transaction_model = CashBookTransaction

    # CONSIDER ADDING A DEFAULT TRANSACTION TYPE
    def get_header_form_type(self):
        t = self.request.GET.get("t", "pi")
        return t


class EditTransaction(SupplierMixin, EditPurchaseOrSalesTransaction):
    header = {
        "model": PurchaseHeader,
        "form": PurchaseHeaderForm,
        "prefix": "header",
        "override_choices": ["supplier"],
    }
    line = {
        "model": PurchaseLine,
        "formset": enter_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "contact_form": ModalSupplierForm(action=reverse_lazy("contacts:create_supplier"), prefix="supplier"),
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


class ViewTransaction(SupplierMixin, ViewTransactionOnLedgerOtherThanNominal):
    header = {
        "model": PurchaseHeader,
        "form": ReadOnlyPurchaseHeaderForm,
        "prefix": "header",
        "override_choices": ["supplier"],
    }
    line = {
        "model": PurchaseLine,
        "formset": read_only_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["item", "nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": read_only_match,
        "prefix": "match"
    }
    void_form_action = reverse_lazy("purchases:void")
    void_form = BaseVoidTransactionForm
    template_name = "purchases/view.html"
    nominal_transaction_model = NominalTransaction
    module = 'PL'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit_view_name"] = "purchases:edit"
        return context


class VoidTransaction(DeleteCashBookTransMixin, BaseVoidTransaction):
    header_model = PurchaseHeader
    matching_model = PurchaseMatching
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("purchases:transaction_enquiry")
    module = 'PL'
    cash_book_transaction_model = CashBookTransaction


class LoadPurchaseMatchingTransactions(LoadMatchingTransactions):
    header_model = PurchaseHeader
    matching_model = PurchaseMatching
    contact_name = "supplier"


class LoadSuppliers(LoadContacts):
    model = Supplier


class TransactionEnquiry(SalesAndPurchasesTransList):
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
    form_field_to_searchable_model_field = {
        "contact": "supplier__name",
        "reference": "ref"
    }
    datetime_fields = ["date", "due_date"]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = SalesAndPurchaseTransactionSearchForm
    contact_name = "supplier"
    template_name = "purchases/transactions.html"

    def get_transaction_url(self, **kwargs):
        row = kwargs.pop("row")
        pk = row["id"]
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
            .order_by(*self.order_by())
        )

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


class AgeCreditorsReport(AgeMatchingReportMixin):
    model = PurchaseHeader
    matching_model = PurchaseMatching
    filter_form = CreditorForm
    form_template = "accountancy/aged_matching_report_form.html"
    template_name = "accountancy/aged_matching_report.html"
    contact_range_field_names = ['from_supplier', 'to_supplier']
    contact_field_name = "supplier"

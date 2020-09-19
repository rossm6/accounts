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
from accountancy.views import (AgeDebtReportMixin, BaseViewTransaction,
                               BaseVoidTransaction,
                               CreatePurchaseOrSalesTransaction,
                               DeleteCashBookTransMixin,
                               EditPurchaseOrSalesTransaction, LoadContacts,
                               LoadMatchingTransactions,
                               SalesAndPurchasesTransList,
                               ViewTransactionOnLedgerOtherThanNominal,
                               ajax_form_validator, create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory,
                               jQueryDataTable,)
from cashbook.models import CashBookTransaction
from items.models import Item
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import (CreditorForm, PurchaseHeaderForm, PurchaseLineForm,
                    QuickSupplierForm, ReadOnlyPurchaseHeaderForm, enter_lines,
                    match, read_only_lines, read_only_match)
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
        "override_choices": ["item", "nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("purchases:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("purchases:create_on_the_fly"), prefix="vat")
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
        "override_choices": ["item", "nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("purchases:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("purchases:create_on_the_fly"), prefix="vat")
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


load_options = input_dropdown_widget_load_options_factory(
    PurchaseLineForm(), 25)


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


validate_choice = input_dropdown_widget_validate_choice_factory(
    PurchaseLineForm())

create_on_the_fly_view = create_on_the_fly(
    nominal={
        "form": NominalForm,
        "prefix": "nominal"
    },
    supplier={
        "form": QuickSupplierForm,
        "prefix": "supplier"
    },
    vat={
        "form": QuickVatForm,
        "serializer": vat_object_for_input_dropdown_widget,
        "prefix": "vat"
    }
)


"""

Page loads - show the default creditors
Submit search form - validate on the server.  If not valid return errors


"""


validate_forms_by_ajax = ajax_form_validator({
    "creditor_form": CreditorForm
})


class AgeCreditorsReport(AgeDebtReportMixin):

    """
    The business logic here is implemented at the Python level so table ordering
    cannot be done at the sql level.  Either disable ordering or implement it at
    the python level...
    """

    model = PurchaseHeader
    template_name = "purchases/creditors.html"
    hide_trans_columns = [
        'supplier',
        'total', 
        'unallocated',
        'current',
        '1 month',
        '2 month',
        '3 month',
        {
            'label': '4 Month & Older',
            'field': '4 month'
        }       
    ]
    show_trans_columns = [
        'supplier',
        'date',
        {
            'label': 'Due Date',
            'field': 'due_date'
        },
        'ref',
        'total',
        'unallocated',
        'current',
        '1 month',
        '2 month',
        '3 month',
        {
            'label': '4 Month & Older',
            'field': '4 month'
        }
    ]

    def get_header_model(self):
        return self.model

    def get_queryset(self):
        return PurchaseHeader.objects.all().select_related('supplier')

    def get_filter_form(self):
        return CreditorForm

    def filter(self, queryset, form):
        from_supplier = form.cleaned_data.get("from_supplier")
        to_supplier = form.cleaned_data.get("to_supplier")
        period = form.cleaned_data.get("period")
        queryset = (
            queryset
            .filter(period__lte=period)
        )
        if from_supplier:
            queryset.filter(supplier__pk__gte=from_supplier.pk)
        if to_supplier:
            queryset.filter(supplier__pk__lte=to_supplier.pk)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = columns = []
        for column in self.show_trans_columns:
            if type(column) is type(""):
                columns.append({
                    "label": column.title(),
                    "field": column
                })
            elif isinstance(column, dict):
                columns.append(column)
        return context
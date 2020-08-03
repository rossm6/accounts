from decimal import Decimal
from functools import reduce
from itertools import chain

from django.contrib import messages
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView
from querystring_parser import parser

from accountancy.forms import AdvancedTransactionSearchForm
from accountancy.views import (CreatePurchaseOrSalesTransaction, EditPurchaseOrSalesTransaction,
                               BaseTransactionsList, BaseViewTransaction,
                               create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory,
                               jQueryDataTable)
from items.models import Item
from nominals.forms import NominalForm
from nominals.models import NominalTransaction
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import (PurchaseHeaderForm, PurchaseLineForm, QuickSupplierForm,
                    ReadOnlyPurchaseHeaderForm,
                    enter_lines, match, read_only_lines, read_only_match, VoidTransaction)
from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


class CreateTransaction(CreatePurchaseOrSalesTransaction):
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
    nominal_model = NominalTransaction
    module = "PL"
    control_account_name = "Purchase Ledger Control"

    # CONSIDER ADDING A DEFAULT TRANSACTION TYPE
    def get_header_form_type(self):
        t = self.request.GET.get("t", "pi")
        return t


class EditTransaction(EditPurchaseOrSalesTransaction):
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
    nominal_model = NominalTransaction
    module = "PL"
    control_account_name = "Purchase Ledger Control"


class ViewTransaction(BaseViewTransaction):
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
    void_form = VoidTransaction
    template_name = "purchases/view.html"


def void(request):
    if request.method == "POST":
        success = False
        form = VoidTransaction(data=request.POST, prefix="void", )
        if form.is_valid():
            success = True
            transaction_to_void = form.instance
            transaction_to_void.status = "v"
            matches = (
                PurchaseMatching.objects
                .filter(Q(matched_to=transaction_to_void) | Q(matched_by=transaction_to_void))
                .select_related("matched_to")
                .select_related("matched_by")
            )
            headers_to_update = []
            headers_to_update.append(transaction_to_void)
            for match in matches:
                if match.matched_by == transaction_to_void:
                    # value is the amount of the matched_to transaction that was matched
                    # e.g. transaction_to_void is 120.00 payment and matched to 120.00 invoice
                    # value = 120.00
                    transaction_to_void.paid += match.value
                    transaction_to_void.due -= match.value
                    match.matched_to.paid -= match.value
                    match.matched_to.due += match.value
                    headers_to_update.append(match.matched_to)
                else:
                    # value is the amount of the transaction_to_void which was matched
                    # matched_by is an invoice for 120.00 and matched_to is a payment for 120.00
                    # value is -120.00
                    transaction_to_void.paid -= match.value
                    transaction_to_void.due += match.value
                    match.matched_by.paid += match.value
                    match.matched_by.due -= match.value
                    headers_to_update.append(match.matched_by)
            PurchaseHeader.objects.bulk_update(
                headers_to_update,
                ["paid", "due", "status"]
            )
            PurchaseMatching.objects.filter(
                pk__in=[match.pk for match in matches]).delete()
            return JsonResponse(
                data={
                    "success": success,
                    "href": reverse("purchases:transaction_enquiry")
                }
            )
        else:
            non_field_errors = form.non_field_errors()
            field_errors = form.errors
            errors = {
                "non_field_errors": non_field_errors,
                "field_errors": field_errors
            }
            return JsonResponse(
                data={
                    "success": success,
                    "errors": errors
                }
            )
    raise Http404("Only post requests are allowed")


class LoadMatchingTransactions(jQueryDataTable, ListView):

    """
    Standard django pagination will not work here
    """

    def get_context_data(self, **kwargs):
        context = {}
        start = self.request.GET.get("start", 0)
        length = self.request.GET.get("length", 25)
        count = queryset = self.get_queryset().count()
        queryset = self.get_queryset()[int(start): int(start) + int(length)]
        data = []
        for obj in queryset:
            data.append(
                {
                    "type": {
                        "label": obj.get_type_display(),
                        "value": obj.type
                    },
                    "ref": obj.ref,
                    "total": obj.total,
                    "paid": obj.paid,
                    "due": obj.due,
                    "DT_RowData": {
                        "pk": obj.pk,
                        "fields": {
                            "type": {
                                'value': obj.type,
                                'order': obj.type
                            },
                            "ref": {
                                'value': obj.ref,
                                'order': obj.ref
                            },
                            "total": {
                                'value': obj.total,
                                'order': obj.total
                            },
                            "paid": {
                                'value': obj.paid,
                                'order': obj.paid
                            },
                            "due": {
                                'value': obj.due,
                                'order': obj.due
                            },
                            "matched_to": {
                                'value': obj.pk,
                                'order': obj.pk
                            }
                        }
                    }
                }
            )
        context["recordsTotal"] = count
        context["recordsFiltered"] = count
        # this would be wrong if we searched !!!
        context["data"] = data
        return context

    def get_queryset(self):
        if supplier := self.request.GET.get("s"):
            q = PurchaseHeader.objects.filter(supplier=supplier).exclude(
                due__exact=0).order_by(*self.order_by())
            if edit := self.request.GET.get("edit"):
                matches = PurchaseMatching.objects.filter(
                    Q(matched_to=edit) | Q(matched_by=edit))
                matches = [(match.matched_by_id, match.matched_to_id)
                           for match in matches]
                matched_headers = list(chain(*matches))
                pk_to_exclude = [header for header in matched_headers]
                # at least exclude the record being edited itself !!!
                pk_to_exclude.append(edit)
                return q.exclude(pk__in=pk_to_exclude).order_by(*self.order_by())
            else:
                return q
        else:
            return PurchaseHeader.objects.none()

    def render_to_response(self, context, **response_kwargs):
        data = {
            "draw": int(self.request.GET.get('draw'), 0),
            "recordsTotal": context["recordsTotal"],
            "recordsFiltered": context["recordsFiltered"],
            "data": context["data"]
        }
        return JsonResponse(data)


class LoadSuppliers(ListView):
    model = Supplier
    paginate_by = 50

    def get_queryset(self):
        if q := self.request.GET.get('q'):
            return (
                Supplier.objects.annotate(
                    similarity=TrigramSimilarity('code', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return Supplier.objects.none()

    def render_to_response(self, context, **response_kwargs):
        suppliers = []
        for supplier in context["page_obj"].object_list:
            s = {
                'code': supplier.code,
                "id": supplier.id
            }
            suppliers.append(s)
        data = {"data": suppliers}
        return JsonResponse(data)


load_options = input_dropdown_widget_load_options_factory(
    PurchaseLineForm(), 25)


class TransactionEnquiry(BaseTransactionsList):
    model = PurchaseHeader
    fields = [
        ("supplier__name", "Supplier"),
        ("ref", "Reference"),
        ("date", "Date"),
        ("due_date", "Due Date"),
        ("paid", "Paid"),
        ("due", "Due")
    ]
    searchable_fields = ["supplier__name", "ref", "total"]
    datetime_fields = ["date", "due_date"]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = AdvancedTransactionSearchForm
    template_name = "purchases/transactions.html"

    def get_transaction_url(self, **kwargs):
        pk = kwargs.pop("pk")
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

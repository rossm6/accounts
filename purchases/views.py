from decimal import Decimal
from functools import reduce
from itertools import chain

from django.contrib import messages
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.views.generic import ListView
from querystring_parser import parser

from accountancy.forms import AdvancedTransactionSearchForm
from accountancy.views import (BaseCreateTransaction, BaseEditTransaction,
                               BaseTransactionsList,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory, jQueryDataTable, create_on_the_fly)
from items.models import Item

from .forms import PurchaseHeaderForm, PurchaseLineForm, enter_lines, match, QuickSupplierForm
from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier

from nominals.forms import NominalForm

from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

class CreateTransaction(BaseCreateTransaction):
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
        "override_choices": ["item", "nominal"] # VAT would not work at the moment
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("purchases:create_on_the_fly"), prefix="vat")
    }
    template_name = "purchases/create.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")


class EditTransaction(BaseEditTransaction):
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
        "override_choices": ["item", "nominal"] # VAT would not work at the moment
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    template_name = "purchases/edit.html"
    success_url = reverse_lazy("purchases:transaction_enquiry")


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
            q = PurchaseHeader.objects.filter(supplier=supplier).exclude(due__exact=0).order_by(*self.order_by())
            if edit := self.request.GET.get("edit"):
                matches = PurchaseMatching.objects.filter(Q(matched_to=edit) | Q(matched_by=edit))
                matches = [ (match.matched_by_id, match.matched_to_id) for match in matches ]
                matched_headers = list(chain(*matches)) # List of primary keys.  Includes the primary key for edit record itself
                return q.exclude(pk__in=[ header for header in matched_headers ]).order_by(*self.order_by())
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
        data = { "data": suppliers }
        return JsonResponse(data)


load_options = input_dropdown_widget_load_options_factory(PurchaseLineForm(), 25)


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
        return reverse_lazy("purchases:edit", kwargs={"pk": pk})

    def get_queryset(self):
        return (
            PurchaseHeader.objects
            .select_related("supplier__name")
            .all()
            .values(
                'id',
                *[ field[0] for field in self.fields ]
            )
            .order_by(*self.order_by())
        )


validate_choice = input_dropdown_widget_validate_choice_factory(PurchaseLineForm())


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
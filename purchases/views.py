from django.contrib.postgres.search import TrigramSimilarity
from django.http import JsonResponse
from django.shortcuts import render, reverse
from django.views.generic import ListView
from querystring_parser import parser

from accountancy.views import (input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)

from .forms import PurchaseHeaderForm, PurchaseLineForm, enter_lines, match
from .models import PurchaseHeader, PurchaseLine, Supplier


def create(request):
    header_form_prefix = "header"
    line_form_prefix = "line"
    matching_form_prefix = "match"
    transaction_type = request.GET.get("t", "i")
    if request.method == "POST":
        header_form = PurchaseHeaderForm(
            data=request.POST,
            prefix=header_form_prefix
        )
        line_formset = enter_lines(
            data=request.POST,
            prefix=line_form_prefix,
            header={}
        )
        matching_formset = match(
            data=request.POST,
            prefix=matching_form_prefix,
            queryset=PurchaseLine.objects.none(),
        )
        # if header_form.is_valid():
        #     if line_formset.is_valid():
        #         line_no = 0
        #         lines = []
        #         header.save()
        #         for form in line_formset.ordered_forms:
        #             if form.empty_permitted and form.has_changed():
        #                 line_no = line_no + 1
        #                 line = form.save(commit=False)
        #                 line.header = header
        #                 line.line_no = line_no
        #                 lines.append(line)
        #         PurchaseLine.objects.bulk_create(lines)
    elif request.method == "GET":
        header_form = PurchaseHeaderForm(
            initial={"type": transaction_type},
            prefix=header_form_prefix
        )
        line_formset = enter_lines(
            prefix=line_form_prefix,
            queryset=PurchaseLine.objects.none()
        )
        matching_formset = match(
            prefix=matching_form_prefix,
            queryset=PurchaseLine.objects.none(),
        )
    return render(
        request,
        "purchases/create.html",
        {
            "header_form": header_form,
            "line_formset": line_formset,
            "matching_formset": matching_formset,
            "line_form_prefix": line_form_prefix, # required by input_grid.js
            "matching_form_prefix": matching_form_prefix # required by matching_js.html
        }
    )


class LoadMatchingTransactions(ListView):

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
            return PurchaseHeader.objects.filter(supplier=supplier).exclude(due__exact=0)
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
                    similarity=TrigramSimilarity('name', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return Supplier.objects.none()
    
    def render_to_response(self, context, **response_kwargs):
        suppliers = []
        for supplier in context["page_obj"].object_list:
            s = {
                'name': supplier.name,
                "id": supplier.id
            }
            suppliers.append(s)
        data = { "data": suppliers }
        return JsonResponse(data)


load_options = input_dropdown_widget_load_options_factory(PurchaseLineForm(), 25)

validate_choice = input_dropdown_widget_validate_choice_factory(PurchaseLineForm())
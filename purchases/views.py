from decimal import Decimal
from itertools import chain
from functools import reduce

from django.contrib import messages
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.views.generic import ListView
from querystring_parser import parser

from accountancy.forms import AdvancedTransactionSearchForm
from accountancy.views import (BaseCreateTransaction,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory, BaseTransactionsList)
from items.models import Item

from .forms import (PaymentHeader, PurchaseHeaderForm, PurchaseLineForm,
                    enter_lines, match)
from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


"""
Successful Posts are slow only because we are rendering all the widgets.  In the end successes
will be redirected so there won't be the need to render all the widgets and if it fails
we already override the choices on the widgets so that it doesn't render thousands.
"""


def index(request):
    """
    Just a page to redirect successful POSTs to for the time being
    """
    return HttpResponse("Post was successful")



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
    }
    match = {
        "model": PurchaseMatching,
        "formset": match,
        "prefix": "match"
    }
    template_name = "purchases/create.html"


def create(request):
    header_form_prefix = "header"
    line_form_prefix = "line"
    matching_form_prefix = "match"
    transaction_type = request.GET.get("t", "i")
    non_field_errors = False
    context = {}
    if request.method == "POST":
        post_successful = False
        line_formset = None
        if transaction_type in ("p", "r", "bp", "br"):
            header_form = PaymentHeader(
                data=request.POST,
                prefix=header_form_prefix
            )
            if header_form.is_valid():
                header = header_form.save(commit=False)
                matching_formset = match(
                    data=request.POST,
                    prefix=matching_form_prefix,
                    queryset=PurchaseMatching.objects.none(),
                    match_by=header
                )
                if matching_formset.is_valid():
                    header.save()
                    matchings = []
                    for form in matching_formset:
                        if form.empty_permitted and form.has_changed():
                            matching = form.save(commit=False)
                            matchings.append(matching)
                    PurchaseHeader.objects.bulk_update(matching_formset.headers, ['due', 'paid'])
                    PurchaseMatching.objects.bulk_create(matchings)
                    # show the user a new input form
                    # might be worth basing this on a user setting in the future
                    # something like "batch mode"
                    # when enabled it shows the user a new form
                    # when disabled it shows the user the new transaction created
                    messages.success(
                        request,
                        'Transaction successfully created' # FIX ME - say 'invoice', 'receipt' etc rather than transaction
                    )
                    post_successful = True
            else:
                if header_form.non_field_errors():
                    non_field_errors = True
                matching_formset = match(
                    data=request.POST,
                    prefix=matching_form_prefix,
                    queryset=PurchaseMatching.objects.none(),
                )
                matching_formset.is_valid()
                if matching_formset.non_form_errors():
                    non_field_errors = True
                for form in matching_formset:
                    if form.non_field_errors():
                        non_field_errors = True
        else:
            header_form = PurchaseHeaderForm(
                data=request.POST,
                prefix=header_form_prefix
            )
            if header_form.is_valid():
                header = header_form.save(commit=False)
                line_formset = enter_lines(
                    data=request.POST,
                    prefix=line_form_prefix,
                    header=header,
                    queryset=PurchaseLine.objects.none()
                )
                context["line_formset"] = line_formset
                matching_formset = match(
                    data=request.POST,
                    prefix=matching_form_prefix,
                    queryset=PurchaseMatching.objects.none(),
                    match_by=header
                )
                if line_formset.is_valid() and matching_formset.is_valid():
                    line_no = 0
                    lines = []
                    header.save()
                    for form in line_formset.ordered_forms:
                        if form.empty_permitted and form.has_changed():
                            line_no = line_no + 1
                            line = form.save(commit=False)
                            line.header = header
                            line.line_no = line_no
                            lines.append(line)
                    matchings = []
                    for form in matching_formset:
                        if form.empty_permitted and form.has_changed():
                            matching = form.save(commit=False)
                            matchings.append(matching)
                    if lines:
                        PurchaseLine.objects.bulk_create(lines)
                    if matchings:
                        # need to update the due amount for the 'matched_to' headers
                        PurchaseHeader.objects.bulk_update(matching_formset.headers, ['due', 'paid'])
                        PurchaseMatching.objects.bulk_create(matchings)
                    # show the user a new input form
                    # might be worth basing this on a user setting in the future
                    # something like "batch mode"
                    # when enabled it shows the user a new form
                    # when disabled it shows the user the new transaction created
                    messages.success(
                        request,
                        'Transaction successfully created' # FIX ME - say 'invoice', 'receipt' etc rather than transaction
                    )
                    post_successful = True
                else:
                    print("either line formset or matching formset is wrong")
            else:
                print("header form is not valid")
                print(header_form.errors)
                if header_form.non_field_errors():
                    non_field_errors = True
                # querysets are .all() for each modelchoicemodel
                # if the querysets contain thousands of objects this will hit performance badly
                # so we need to override the querysets AFTER checking if the forms are valid (obviously need full querysets for this)
                chosen_supplier = header_form.cleaned_data.get("supplier")
                if chosen_supplier:
                    field = header_form.fields['supplier']
                    field.widget.choices = [ (chosen_supplier.pk, str(chosen_supplier)) ]
                line_formset = enter_lines(
                    data=request.POST,
                    prefix=line_form_prefix,
                    queryset=PurchaseLine.objects.none()
                )
                context["line_formset"] = line_formset
                line_formset.is_valid()
                if line_formset.non_form_errors():
                    non_field_errors = True
                for form in line_formset:
                    if form.non_field_errors():
                        non_field_errors = True
                matching_formset = match(
                    data=request.POST,
                    prefix=matching_form_prefix,
                    queryset=PurchaseMatching.objects.none(),
                )
                matching_formset.is_valid()
                if matching_formset.non_form_errors():
                    non_field_errors = True
                for form in matching_formset:
                    if form.non_field_errors():
                        non_field_errors = True


        # override the choices so that it doesn't take so long to render

        chosen_supplier = header_form.cleaned_data.get("supplier")
        if chosen_supplier:
            field = header_form.fields['supplier']
            field.widget.choices = [ (chosen_supplier.pk, str(chosen_supplier)) ]

        if line_formset:
            for form in line_formset:
                item = form.cleaned_data.get("item")
                field = form.fields["item"]
                if item:
                    field.widget.choices = [ (item.pk, str(item)) ]
                else:
                    field.widget.choices = []
                nominal = form.cleaned_data.get("nominal")
                field = form.fields["nominal"]
                if nominal:
                    field.widget.choices = [ (nominal.pk, str(nominal)) ]
                else:
                    field.widget.choices = []


        if post_successful:
            return redirect(reverse("purchases:index"))


    elif request.method == "GET":
        if transaction_type in ("p", "r", "bp", "br"):
            header_form = PaymentHeader(
                initial={"type": transaction_type, "total": 0},
                prefix=header_form_prefix,
            )
        else:
            header_form = PurchaseHeaderForm(
                initial={"type": transaction_type, "total": 0},
                prefix=header_form_prefix
            )
            line_formset = enter_lines(
                prefix=line_form_prefix,
                queryset=PurchaseLine.objects.none()
            )
            context["line_formset"] = line_formset
        matching_formset = match(
            prefix=matching_form_prefix,
            queryset=PurchaseLine.objects.none(),
        )
    context["header_form"] = header_form
    context["matching_formset"] = matching_formset
    context["line_form_prefix"] = line_form_prefix
    context["matching_form_prefix"] = matching_form_prefix
    return render(
        request,
        "purchases/create.html",
        context
    )



# we need to create some tests where the header_form fails
# and the other forms fail too

def edit(request, **kwargs):
    pk = kwargs.get("pk")
    header_form_prefix = "header"
    line_form_prefix = "line"
    match_form_prefix= "match"
    context = {}
    context["edit"] = pk
    header = get_object_or_404(PurchaseHeader, pk=pk)
    context["header_form_prefix"] = header_form_prefix
    context["line_form_prefix"] = line_form_prefix
    context["matching_form_prefix"] = match_form_prefix
    context["payment_form"] = False
    if header.type in ('bp', 'p', 'br', 'r'):
        context["payment_form"] = True
    if request.method == "GET":
        header_form = PurchaseHeaderForm(prefix=header_form_prefix, instance=header)
        context["header_form"] = header_form
        line_formset = enter_lines(
            prefix=line_form_prefix,
            queryset=PurchaseLine.objects.filter(header=header)
        )
        context["line_formset"] = line_formset
        match_formset = match(
            prefix=match_form_prefix,
            queryset=(
                PurchaseMatching.objects
                .filter(Q(matched_by=header) | Q(matched_to=header))
                .select_related('matched_by')
                .select_related('matched_to')
            ),
            match_by=header,
            auto_id=False
        )
        context["matching_formset"] = match_formset
    if request.method == "POST":
        header_form = PurchaseHeaderForm(data=request.POST, prefix=header_form_prefix, instance=header)
        context["header_form"] = header_form 
        if header_form.is_valid():
            header = header_form.save(commit=False)
            if header.type in ('p', 'bp', 'r', 'br'):
                # do no consider lines
                match_formset = match(
                    data=request.POST,
                    prefix=match_form_prefix,
                    queryset=(
                        PurchaseMatching.objects
                        .filter(Q(matched_by=header) | Q(matched_to=header))
                        .select_related('matched_by')
                        .select_related('matched_to')
                    ),
                    match_by=header,
                    auto_id=False
                )
                context["matching_formset"] = match_formset
                if match_formset.is_valid():
                    header.save() # perhaps put this in the headers_to_update set also
                    match_formset.save(commit=False)
                    PurchaseMatching.objects.bulk_create(match_formset.new_objects)
                    PurchaseMatching.objects.bulk_update(
                        [ obj for obj, _tuple in match_formset.changed_objects ], 
                        [ 'value' ]
                    )
                    PurchaseHeader.objects.bulk_update(match_formset.headers, ['due', 'paid'])
                    return redirect(reverse("purchases:index"))
                else:
                    print("payment matching invalid")
                    # override the choices so that it doesn't take so long to render
                    chosen_supplier = header_form.cleaned_data.get("supplier")
                    if chosen_supplier:
                        field = header_form.fields['supplier']
                        field.widget.choices = [ (chosen_supplier.pk, str(chosen_supplier)) ]
                    match_formset = match(
                        data=request.POST,
                        prefix=match_form_prefix,
                        queryset=(
                            PurchaseMatching.objects
                            .filter(Q(matched_by=header) | Q(matched_to=header))
                            .select_related('matched_by')
                            .select_related('matched_to')
                        ),
                        match_by=header,
                    )
                    context["matching_formset"] = match_formset
                    match_formset.is_valid()
                    if match_formset.non_form_errors():
                        non_field_errors = True
                    for form in match_formset:
                        if form.non_field_errors():
                            non_field_errors = True
            else:
                line_formset = enter_lines(
                    data=request.POST,
                    prefix=line_form_prefix,
                    header=header,
                    queryset=PurchaseLine.objects.filter(header=header)
                )
                context["line_formset"] = line_formset
                match_formset = match(
                    data=request.POST,
                    prefix=match_form_prefix,
                    queryset=(
                        PurchaseMatching.objects
                        .filter(Q(matched_by=header) | Q(matched_to=header))
                        .select_related('matched_by')
                        .select_related('matched_to')
                    ),
                    match_by=header,
                    auto_id=False
                )
                context["matching_formset"] = match_formset
                print("is it valid")
                if line_formset.is_valid() and match_formset.is_valid():
                    header.save()
                    line_formset.save(commit=False)
                    line_no = 1
                    # WE PROGRAM DEFENSIVELY HERE IN CASE VALID BUT EMPTY FORMS
                    # ARE INCLUDED IN ORDERED_FORMS
                    for form in line_formset.ordered_forms: # user can still order in edit view
                        if form.empty_permitted and form.has_changed():
                            form.instance.header = header
                            form.instance.line_no = line_no
                            line_no = line_no + 1
                        elif not form.empty_permitted:
                            form.instance.line_no = line_no
                            line_no = line_no + 1
                    # matching formset
                    match_formset.save(commit=False)
                    PurchaseMatching.objects.bulk_create(match_formset.new_objects)
                    PurchaseMatching.objects.bulk_update(
                        [ obj for obj, _tuple in match_formset.changed_objects ], 
                        [ 'value' ]
                    )
                    PurchaseHeader.objects.bulk_update(match_formset.headers, ['due', 'paid'])
                    PurchaseLine.objects.bulk_create(line_formset.new_objects)
                    PurchaseLine.objects.bulk_update(
                        [ obj for obj, _tuple in line_formset.changed_objects ],
                        [ 'line_no', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat' ]
                    )
                    PurchaseLine.objects.filter(pk__in=[ line.pk for line in line_formset.deleted_objects  ]).delete()
                    context["line_formset"] = line_formset
                    context["match_formset"] = match_formset
                    return redirect(reverse("purchases:index"))
                else:
                    print("not valid lines or matching")
                    line_formset = enter_lines(
                        data=request.POST,
                        prefix=line_form_prefix,
                        header=header,
                        queryset=PurchaseLine.objects.filter(header=header)
                    )
                    context["line_formset"] = line_formset
                    line_formset.is_valid()
                    if line_formset.non_form_errors():
                        non_field_errors = True
                    for form in line_formset:
                        if form.non_field_errors():
                            non_field_errors = True
                    match_formset = match(
                        data=request.POST,
                        prefix=match_form_prefix,
                        queryset=(
                            PurchaseMatching.objects
                            .filter(Q(matched_by=header) | Q(matched_to=header))
                            .select_related('matched_by')
                            .select_related('matched_to')
                        ),
                        match_by=header,
                    )
                    context["matching_formset"] = match_formset
                    match_formset.is_valid()
                    if match_formset.non_form_errors():
                        non_field_errors = True
                    for form in match_formset:
                        if form.non_field_errors():
                            non_field_errors = True

                    chosen_supplier = header_form.cleaned_data.get("supplier")
                    if chosen_supplier:
                        field = header_form.fields['supplier']
                        field.widget.choices = [ (chosen_supplier.pk, str(chosen_supplier)) ]

                    if line_formset:
                        for form in line_formset:
                            item = form.cleaned_data.get("item")
                            field = form.fields["item"]
                            if item:
                                field.widget.choices = [ (item.pk, str(item)) ]
                            else:
                                field.widget.choices = []
                            nominal = form.cleaned_data.get("nominal")
                            field = form.fields["nominal"]
                            if nominal:
                                field.widget.choices = [ (nominal.pk, str(nominal)) ]
                            else:
                                field.widget.choices = []

        else:
            print("header form is not valid")
            print(header_form.errors)
            if header_form.non_field_errors():
                non_field_errors = True
            line_formset = enter_lines(
                data=request.POST,
                prefix=line_form_prefix,
                header=header, # HEADER IS THE OBJECT PULLED OUT OF THE DB.  NOT THE ONE FROM THE FORM WHICH DID NOT VALIDATE. SEE TOP OF THE VIEW
                queryset=PurchaseLine.objects.filter(header=header)
            )
            context["line_formset"] = line_formset
            match_formset = match(
                data=request.POST,
                prefix=match_form_prefix,
                queryset=(
                    PurchaseMatching.objects
                    .filter(Q(matched_by=header) | Q(matched_to=header))
                    .select_related('matched_by')
                    .select_related('matched_to')
                ),
                match_by=header, # HEADER IS THE OBJECT PULLED OUT OF THE DB.  NOT THE ONE FROM THE FORM WHICH DID NOT VALIDATE
                auto_id=False
            )
            context["matching_formset"] = match_formset
            # override the choices so that it doesn't take so long to render
            chosen_supplier = header_form.cleaned_data.get("supplier")
            if chosen_supplier:
                field = header_form.fields['supplier']
                field.widget.choices = [ (chosen_supplier.pk, str(chosen_supplier)) ]
    return render(
        request,
        "purchases/edit.html",
        context
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
            q = PurchaseHeader.objects.filter(supplier=supplier).exclude(due__exact=0)
            if edit := self.request.GET.get("edit"):
                matches = PurchaseMatching.objects.filter(Q(matched_to=edit) | Q(matched_by=edit))
                matches = [ (match.matched_by_id, match.matched_to_id) for match in matches ]
                matched_headers = list(chain(*matches)) # List of primary keys.  Includes the primary key for edit record itself
                return q.exclude(pk__in=[ header for header in matched_headers ])
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
import functools
from copy import deepcopy
from datetime import date
from itertools import chain, groupby

from crispy_forms.utils import render_crispy_form
from django.conf import settings
from django.contrib import messages
from django.contrib.postgres.search import (SearchQuery, SearchRank,
                                            SearchVector, TrigramSimilarity)
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, Sum
from django.http import (Http404, HttpResponse, HttpResponseForbidden,
                         HttpResponseRedirect, JsonResponse)
from django.shortcuts import get_object_or_404, render, reverse
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.views.generic import ListView, View
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from querystring_parser import parser

from accountancy.exceptions import FormNotValid
from accountancy.helpers import JSONBlankDate, Period, sort_multiple
from nominals.models import Nominal

from .widgets import InputDropDown


def format_dates(objects, date_keys, format):
    """
    Convert date or datetime objects to the format specified.
    """
    for obj in objects:
        for key in obj:
            if key in date_keys:
                try:
                    string_format = obj[key].strftime(format)
                    obj[key] = string_format
                except AttributeError:
                    pass


def get_search_vectors(searchable_fields):
    search_vectors = [
        SearchVector(field)
        for field in searchable_fields
    ]
    return functools.reduce(lambda a, b: a + b, search_vectors)


def get_trig_vectors(searchable_fields, search_text):
    trig_vectors = [
        TrigramSimilarity(field, search_text)
        for field in searchable_fields
    ]
    return functools.reduce(lambda a, b: a + b, trig_vectors)


def get_trig_vectors_for_different_inputs(fields_and_inputs):
    trig_vectors = [
        TrigramSimilarity(field, _input)
        for field, _input in fields_and_inputs
    ]
    return functools.reduce(lambda a, b: a + b, trig_vectors)


def input_dropdown_widget_validate_choice_factory(form):
    """

    Given a form which contains input dropdown widgets
    this will return a view which can be called via ajax
    to validate a choice selected in the widget.

    """

    def validate(request):
        data = {}
        data["success"] = False
        if field := request.GET.get("field"):
            if value := request.GET.get("value"):
                form_field = form.fields[field]
                if instance := form_field.post_queryset.filter(pk=value):
                    instance = instance[0]
                    data["success"] = True
                    data["value"] = instance.pk
                    data["label"] = str(instance)
                    return JsonResponse(data)
                else:
                    return JsonResponse(data)
            else:
                return JsonResponse(data)
        else:
            return JsonResponse(data)

    return validate


def input_dropdown_widget_load_options_factory(form, paginate_by):
    """
    Forms, or formsets, which have multiple
    input dropdown widgets, need a single view
    to call view AJAX for populating the dropdown
    menu either via new search or scroll.

    This functions takes a form and returns
    such a view.

    This will take care of only showing the empty label
    if it is the first page which is requested.  The client
    has the responsibility of filtering through the dom elements
    returned though.  At least one thing which will want to be
    left out for page numbers greater than 1 is the New Item
    link.
    """

    def load(request):
        if field := request.GET.get("field"):
            try:
                queryset = form.fields[field].load_queryset
            except AttributeError:
                raise Http404("Load Queryset not found")
            except KeyError:
                raise Http404("No such field found")
            if search := request.GET.get("search"):
                try:
                    searchable_fields = form.fields[field].searchable_fields
                except AttributeError:
                    raise Http404("No searchfields found for searching")
                queryset = (
                    queryset.annotate(
                        search=get_search_vectors(searchable_fields)
                    )
                    .filter(search=search)
                )
            paginator = Paginator(queryset, paginate_by)
            page_number = request.GET.get('page', 1)
            try:
                page_obj = paginator.page(page_number)
            except PageNotAnInteger:
                page_obj = paginator.page(1)
            except EmptyPage:
                page_obj = paginator.page(1)
                page_obj.object_list = queryset.none()
                page_obj.has_other_pages = False
            form_field = deepcopy(form.fields[field])
            widget = form_field.widget
            if int(page_number) > 1:
                form_field.empty_label = None
            iterator = form_field.iterator
            form_field.queryset = page_obj.object_list
            widget.choices = iterator(form_field)
            field_value = request.GET.get("value", "")
            # the widget will add a data-selected attribute
            # to the option which has value matching this field_value
            return render(
                request,
                widget.template_name,
                widget.get_context(str(field), field_value, widget.attrs)
            )
        else:
            raise Http404("No field specified")

    return load


class jQueryDataTable:

    def order_objects(self, objs):
        """
        Sometimes it is not possible in Django to use the ORM, or it would be tricky,
        so we have to order in python.
        """
        orm_ordering = self.order_by()  # so we don't repeat ourselves
        ordering = []
        for order in orm_ordering:
            if order[0] == "-":
                field = order[1:]
                ordering.append(
                    (lambda obj: obj.get(field), True)  # descending
                )
            else:
                field = order
                ordering.append(
                    (lambda obj: obj.get(field), False)  # ascending
                )
        return sort_multiple(objs, *ordering)

    def order_by(self):
        ordering = []  # will pass this to ORM to order the fields correctly
        # create objects out of GET params
        d = parser.parse(self.request.GET.urlencode())
        improved = {}
        for key in d:
            val = d[key]
            if isinstance(val, dict):
                val = list(val.values())
            improved[key] = val
        self.GET = improved
        orders = self.GET.get("order", [])
        columns = self.GET.get("columns", [])
        if orders:
            for order in orders:
                column_index = order.get("column")
                try:
                    column_index = int(column_index)
                except:
                    break
                if column_index >= 0:
                    try:
                        column = columns[column_index]
                        field_name = column.get("data")
                        if field_name:
                            order_by = order.get("dir")
                            if order_by in ["asc", "desc"]:
                                ordering.append(
                                    ("" if order_by == "asc" else "-") + field_name
                                )
                    except IndexError as e:
                        break
        return ordering


class SalesAndPurchaseSearchMixin:
    def apply_advanced_search(self, cleaned_data):
        contact = cleaned_data.get("contact")
        reference = cleaned_data.get("reference")
        total = cleaned_data.get("total")
        period = cleaned_data.get("period")
        search_within = cleaned_data.get("search_within")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        queryset = self.get_queryset()

        if contact or reference:
            queryset = (
                queryset.annotate(
                    similarity=(
                        get_trig_vectors_for_different_inputs(
                            self.get_list_of_search_values_for_model_attributes(
                                cleaned_data)
                        )
                    )
                ).filter(similarity__gt=0.5)
            )
        if total:
            queryset = queryset.filter(total=total)
        if period:
            queryset = queryset.filter(period=period)
        if start_date:
            q_object_start_date = Q()
            if search_within == "any" or search_within == "tran":
                q_object_start_date |= Q(date__gte=start_date)
            if search_within == "any" or search_within == "due":
                q_object_start_date |= Q(due_date__gte=start_date)
            queryset = queryset.filter(q_object_start_date)
        if end_date:
            q_object_end_date = Q()
            if search_within == "any" or search_within == "tran":
                q_object_end_date |= Q(date__lte=end_date)
            if search_within == "any" or search_within == "due":
                q_object_end_date |= Q(due_date__lte=end_date)
            queryset = queryset.filter(q_object_end_date)
        return queryset


class NominalSearchMixin:
    def apply_advanced_search(self, cleaned_data):
        nominal = cleaned_data.get("nominal")
        reference = cleaned_data.get("reference")
        total = cleaned_data.get("total")
        period = cleaned_data.get("period")
        date = cleaned_data.get("date")
        queryset = self.get_queryset()

        if nominal or reference:
            queryset = (
                queryset.annotate(
                    similarity=(
                        get_trig_vectors_for_different_inputs(
                            self.get_list_of_search_values_for_model_attributes(
                                cleaned_data)
                        )
                    )
                ).filter(similarity__gt=0.5)
            )
        if total:
            queryset = queryset.filter(total=total)
        if period:
            queryset = queryset.filter(period=period)
        if date:
            queryset = queryset.filter(date=date)
        return queryset


class BaseTransactionsList(jQueryDataTable, ListView):

    def get_list_of_search_values_for_model_attributes(self, form_cleaned_data):
        return [
            (model_field, form_cleaned_data.get(form_field, ""))
            for form_field, model_field in self.form_field_to_searchable_model_field.items()
        ]

    def exclude_from_queryset(self, queryset):
        return queryset

    def apply_advanced_search(self, cleaned_data):
        raise NotImplementedError

    def get_form_kwargs(self):
        kwargs = {
            "data": self.request.GET,
        }
        return kwargs

    def get_search_form(self):
        return self.advanced_search_form_class(
            **self.get_form_kwargs()
        )

    def get_context_data(self, **kwargs):
        context_data = {}
        context_data["columns"] = [field[0] for field in self.fields]
        context_data["column_labels"] = [field[1] for field in self.fields]
        if self.request.is_ajax() and self.request.method == "GET" and self.request.GET.get('use_adv_search'):
            form = self.get_search_form()
            # form = AdvancedTransactionSearchForm(data=self.request.GET)
            # This form was not validating despite a valid datetime being entered on the client
            # The problem was jquery.serialize encodes
            # And on top of this jQuery datatable does also
            # solution on client - do not use jQuery.serialize
            if form.is_valid():
                queryset = self.apply_advanced_search(form.cleaned_data)
                if not form.cleaned_data["include_voided"]:
                    self.exclude_from_queryset(queryset)
            else:
                queryset = self.get_queryset()
                self.exclude_from_queryset(queryset)
        else:
            context_data["form"] = self.get_search_form()
            queryset = self.get_queryset()
            self.exclude_from_queryset(queryset)
        start = self.request.GET.get("start", 0)
        paginate_by = self.request.GET.get("length", 25)
        p = Paginator(queryset, paginate_by)
        trans_count = p.count
        page_number = int(int(start) / int(paginate_by)) + 1
        try:
            page_obj = p.page(page_number)
        except PageNotAnInteger:
            page_obj = p.page(1)
        except EmptyPage:
            page_obj = p.page(1)
            page_obj.object_list = self.get_queryset().none()
            page_obj.has_other_pages = False
        context_data["paginator_obj"] = p
        context_data["page_obj"] = page_obj
        rows = []

        if identifier := hasattr(self, 'row_identifier'):
            identifier = self.row_identifier
        else:
            identifier = 'id'

        for row in page_obj.object_list:
            row["DT_RowData"] = {
                "pk": row.get(identifier),
                "href": self.get_transaction_url(row=row)
            }
            rows.append(row)
        format_dates(rows, self.datetime_fields, self.datetime_format)
        context_data["data"] = rows
        return context_data

    def render_to_response(self, context, **response_kwargs):
        if self.request.is_ajax():
            data = {
                "draw": int(self.request.GET.get('draw'), 0),
                "recordsTotal": context["paginator_obj"].count,
                "recordsFiltered": context["paginator_obj"].count,
                "data": context["data"]
            }
            return JsonResponse(data)
        return super().render_to_response(context, **response_kwargs)


class SalesAndPurchasesTransList(SalesAndPurchaseSearchMixin, BaseTransactionsList):

    def exclude_from_queryset(self, queryset):
        return queryset.exclude(status="v")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["contact_name"] = self.contact_name
        return kwargs


class NominalTransList(NominalSearchMixin, BaseTransactionsList):
    pass


class RESTBaseTransactionMixin:

    def get_nominal_model(self):
        return self.nominal_model

    def get_nominal_transaction_model(self):
        return self.nominal_transaction_model

    def create_or_update_related_transactions(self, **kwargs):
        self.create_or_update_nominal_transactions(**kwargs)

    def get_transaction_type_object(self):
        if hasattr(self, "transaction_type_object"):
            return self.tranaction_type_object
        else:
            self.transaction_type_object = self.header_obj.get_type_transaction()
            return self.transaction_type_object

    def get_module(self):
        return self.module

    def lines_should_be_ordered(self):
        if hasattr(self, "line"):
            return self.line.get("can_order", True)

    def get_header_prefix(self):
        return self.header.get('prefix', 'header')

    def get_header_form_kwargs(self):
        kwargs = {
            'prefix': self.get_header_prefix()
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
            })

        return kwargs

    def get_header_form(self):
        if hasattr(self, "header_form"):
            return self.header_form
        form_class = self.header.get('form')
        self.header_form = form_class(**self.get_header_form_kwargs())
        return self.header_form

    def requires_analysis(self, header_form):
        if hasattr(header_form, "cleaned_data"):
            if t := header_form.cleaned_data.get("type"):
                if t in self.get_header_model().get_types_requiring_analysis():
                    return True
                else:
                    return False
        if t := self.header_form.initial.get('type'):
            if t in self.get_header_model().get_types_requiring_analysis():
                return True
            # we need this because read only forms used for the detail transaction view
            # convert the initial choice value to the choice label
            if t in self.get_header_model().get_type_names_requiring_analysis():
                return True
        else:
            return False

    def get_header_model(self):
        return self.header.get('model')

    def requires_lines(self, header_form):
        if hasattr(header_form, "cleaned_data"):
            if t := header_form.cleaned_data.get("type"):
                if t in self.get_header_model().get_types_requiring_lines():
                    return True
                else:
                    return False
        if t := self.header_form.initial.get('type'):
            if t in self.get_header_model().get_types_requiring_lines():
                return True
            # we need this because read only forms used for the detail transaction view
            # convert the initial choice value to the choice label
            if t in self.get_header_model().get_type_names_requiring_lines():
                return True
        else:
            return False

    def get_line_model(self):
        return self.line.get('model')

    def get_line_formset_queryset(self):
        return self.get_line_model().objects.none()

    def get_line_prefix(self):
        if hasattr(self, 'line'):
            return self.line.get('prefix', 'line')

    def get_line_formset_kwargs(self, header=None):

        kwargs = {
            'prefix': self.get_line_prefix(),
            'queryset': self.get_line_formset_queryset()
        }

        if self.request.method in ('POST', 'PUT'):
            # passing in data will mean the form will use the POST queryset
            # which means potentially huge choices rendered on the client
            if self.requires_lines(self.header_form):
                kwargs.update({
                    'data': self.request.POST
                })
            kwargs.update({
                'header': header
            })

        if (self.requires_lines(self.header_form) and not self.requires_analysis(self.header_form)):
            brought_forward = True
        else:
            brought_forward = False

        kwargs["brought_forward"] = brought_forward
        # need to tell the formset the forms contained should have the nominal and vat code field hidden

        return kwargs

    def get_line_formset(self, header=None):
        if hasattr(self, 'line'):
            if hasattr(self, 'line_formset'):
                return self.line_formset
            else:
                formset_class = self.line.get('formset')
                return formset_class(**self.get_line_formset_kwargs(header))

    def matching_is_invalid(self):
        self.match_formset = self.get_match_formset()
        if self.match_formset:
            self.match_formset.is_valid()
            if self.match_formset.non_form_errors():
                self.non_field_errors = True
            for form in self.match_formset:
                if form.non_field_errors():
                    self.non_field_errors = True

    def lines_are_invalid(self):
        self.line_formset = self.get_line_formset()

        if self.line_formset:
            self.line_formset.is_valid()
            # validation may have been called already but Django will not run full_clean
            # again if so
            # see is_valid method at - https://github.com/django/django/blob/master/django/forms/forms.py
            if self.line_formset.non_form_errors():
                self.non_field_errors = True
            for form in self.line_formset:
                if form.non_field_errors():
                    self.non_field_errors = True

        if self.line_formset:
            if override_choices := self.line.get('override_choices'):
                for form in self.line_formset:
                    for choice in override_choices:
                        field = form.fields[choice]
                        if chosen := form.cleaned_data.get(choice):
                            field.widget.choices = [(chosen.pk, str(chosen))]
                        else:
                            field.widget.choices = []

    def header_is_invalid(self):
        if self.header_form.non_field_errors():
            self.non_field_errors = True

        if override_choices := self.header.get('override_choices'):
            form = self.header_form
            for choice in override_choices:
                field = form.fields[choice]
                if chosen := form.cleaned_data.get(choice):
                    field.widget.choices = [(chosen.pk, str(chosen))]
                else:
                    field.widget.choices = []

    def invalid_forms(self):
        self.header_is_invalid()
        if self.requires_lines(self.get_header_form()):
            self.lines_are_invalid()
        self.matching_is_invalid()
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        """

        This is for CB and NL at the moment only !!!

        Handle POST requests: instantiate forms with the passed POST variables
        and then check if it is valid

        WARNING - LINE FORMSET MUST BE VALIDATED BEFORE MATCH FORMSET

        """
        self.header_form = self.get_header_form()
        if self.header_form.is_valid():
            # changed name from header because this is a cls attribute of course
            self.header_obj = self.header_form.save(commit=False)
            self.line_formset = self.get_line_formset(self.header_obj)
            if self.line_formset.is_valid():
                self.lines_are_valid()
            else:
                return self.invalid_forms()
        else:
            return self.invalid_forms()
        return self.get_successful_response()


class BaseTransaction(RESTBaseTransactionMixin, TemplateResponseMixin, ContextMixin, View):

    def get_successful_response(self):
        messages.success(
            self.request,
            self.get_success_message()
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        if creation_type := self.request.POST.get('approve'):
            if creation_type == "add_another":
                # the relative path including the GET parameters e.g. /purchases/create?t=i
                return self.request.get_full_path()
        return self.success_url

    def get_context_data(self, **kwargs):
        # FIX ME - change 'matching_formset" to "match_formset" in the template

        if 'header_form' not in kwargs:
            kwargs["header_form"] = self.get_header_form()

        if 'matching_formset' not in kwargs:
            kwargs["matching_formset"] = self.get_match_formset()
        if 'header_prefix' not in kwargs:
            kwargs['header_form_prefix'] = self.get_header_prefix()

        if self.requires_lines(kwargs["header_form"]):
            if 'line_form_prefix' not in kwargs:
                kwargs["line_form_prefix"] = self.get_line_prefix()
            if 'line_formset' not in kwargs:
                kwargs["line_formset"] = self.get_line_formset()

        if 'matching_form_prefix' not in kwargs:
            kwargs["matching_form_prefix"] = self.get_match_prefix()
        if 'non_field_errors' not in kwargs:
            if hasattr(self, 'non_field_errors'):
                kwargs['non_field_errors'] = self.non_field_errors

        if 'transaction_type' not in kwargs:
            kwargs['transaction_type'] = "debit" if self.type_is_debit() else "credit"

        if hasattr(self, 'create_on_the_fly'):
            for form in self.create_on_the_fly:
                # this is a form instance already
                kwargs[form] = self.create_on_the_fly[form]

        return super().get_context_data(**kwargs)

    def get_match_model(self):
        return self.match.get('model')

    def get_match_prefix(self):
        if hasattr(self, 'match'):
            return self.match.get('prefix', 'match')

    def get_match_formset_queryset(self):
        return self.get_match_model().objects.none()

    def get_match_formset_kwargs(self, header=None):

        kwargs = {
            'prefix': self.get_match_prefix(),
            'queryset': self.get_match_formset_queryset(),
            'match_by': header
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
            })

        return kwargs

    def get_match_formset(self, header=None):
        if hasattr(self, 'match'):
            if hasattr(self, 'match_formset'):
                return self.match_formset
            else:
                formset_class = self.match.get('formset')
                return formset_class(**self.get_match_formset_kwargs(header))

    # MIGHT BE OBSOLETE NOW
    def header_is_payment_type(self):
        return self.header_obj.type in ("pbp", "pp", "pbr", "pr")

    def type_is_debit(self):
        if t := self.header_form.instance.type:
            pass
        elif t := self.header_form.initial.get("type"):
            pass
        # if type is '' then user abusing UI so stuff them
        if t in self.get_header_model().get_debit_types():
            return True
        else:
            return False

    def get(self, request, *args, **kwargs):
        """ Handle GET requests: instantiate a blank version of the form. """
        return self.render_to_response(self.get_context_data())


class RESTBaseCreateTransactionMixin:

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        # add nom trans as attribute so API response can return in JSON response
        # for python api client
        self.nom_trans = transaction_type_object.create_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )

    def lines_are_valid(self):
        line_no = 1
        lines = []
        self.header_obj.save()
        self.header_has_been_saved = True
        line_forms = self.line_formset.ordered_forms if self.lines_should_be_ordered(
        ) else self.line_formset
        for form in line_forms:
            if form.empty_permitted and form.has_changed():
                line = form.save(commit=False)
                line.header = self.header_obj
                line.line_no = line_no
                lines.append(line)
                line_no = line_no + 1
        if lines:
            self.lines = self.get_line_model().objects.bulk_create(lines)
            self.create_or_update_related_transactions(lines=lines)

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if self.request.method in ('GET'):
            kwargs["initial"] = {
                "type": self.get_header_form_type()
            }
        return kwargs


class BaseCreateTransaction(RESTBaseCreateTransactionMixin, BaseTransaction):

    def get_success_message(self):
        return "Transaction was created successfully."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["create"] = True  # some javascript templates depend on this
        return context

    def matching_is_valid(self):
        # Q - This flag may be obsolete now
        if not hasattr(self, 'header_has_been_saved'):
            self.header_obj.save()
        matches = []
        for form in self.match_formset:
            if form.empty_permitted and form.has_changed():
                match = form.save(commit=False)
                if match.value != 0:
                    matches.append(match)
        if matches:
            self.get_header_model().objects.bulk_update(
                self.match_formset.headers,
                ['due', 'paid']
            )
            self.get_match_model().objects.bulk_create(matches)


class CreateCashBookEntriesMixin:

    def get_cash_book_transaction_model(self):
        return self.cash_book_transaction_model

    def create_or_update_cash_book_transactions(self, **kwargs):
        self.transaction_type_object.create_cash_book_entry(
            self.get_cash_book_transaction_model(),
            **kwargs
        )

    def create_or_update_related_transactions(self, **kwargs):
        super().create_or_update_related_transactions(**kwargs)
        self.create_or_update_cash_book_transactions(**kwargs)


class CreateCashBookTransaction(CreateCashBookEntriesMixin, BaseCreateTransaction):
    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        transaction_type_object = self.get_transaction_type_object()
        # e.g. Payment, Refund
        transaction_type_object.create_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )


class MatchingMixin:
    def post(self, request, *args, **kwargs):
        """

        Handle POST requests: instantiate forms with the passed POST variables
        and then check if it is valid

        WARNING - LINE FORMSET MUST BE VALIDATED BEFORE MATCH FORMSET

        """

        self.header_form = self.get_header_form()
        if self.header_form.is_valid():
            # changed name from header because this is a cls attribute of course
            self.header_obj = self.header_form.save(commit=False)
            self.line_formset = self.get_line_formset(self.header_obj)
            self.match_formset = self.get_match_formset(self.header_obj)
            if not self.requires_lines(self.header_form):
                if self.match_formset.is_valid():
                    self.header_obj.save()
                    self.header_has_been_saved = True
                    # FIX ME - implement get_module and get_account_name methods
                    self.create_or_update_related_transactions()
                    self.matching_is_valid()
                    messages.success(
                        request,
                        self.get_success_message()
                    )
                else:
                    return self.invalid_forms()
            else:
                if self.line_formset and self.match_formset:
                    if self.line_formset.is_valid() and self.match_formset.is_valid():
                        # has to come before matching_is_valid because this formset could alter header_obj
                        self.lines_are_valid()
                        self.matching_is_valid()
                        messages.success(
                            request,
                            self.get_success_message()
                        )
                    else:
                        return self.invalid_forms()
        else:
            return self.invalid_forms()

        return HttpResponseRedirect(self.get_success_url())


class CreatePurchaseOrSalesTransaction(MatchingMixin, CreateCashBookEntriesMixin, BaseCreateTransaction):

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "control_nominal_name": self.control_nominal_name,
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        transaction_type_object.create_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )


class RESTIndividualTransactionForHeaderMixin:
    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if not hasattr(self, 'header_to_edit'):
            raise AttributeError(
                f"{self.__class__.__name__} has no 'header_to_edit' attribute.  Did you override "
                "setup() and forget to class super()?"
            )
        kwargs["instance"] = self.header_to_edit
        return kwargs


class RESTIndividualTransactionMixin:

    def get_line_formset_kwargs(self, header=None):
        kwargs = super().get_line_formset_kwargs(header)
        if not header:
            kwargs["header"] = self.header_to_edit
        return kwargs

    def get_line_formset_queryset(self):
        return self.get_line_model().objects.filter(header=self.header_to_edit)

    def get_match_formset_queryset(self):
        return (
            self.get_match_model()
            .objects
            .filter(Q(matched_by=self.header_to_edit) | Q(matched_to=self.header_to_edit))
            .select_related('matched_by')
            .select_related('matched_to')
        )

    def get_match_formset(self, header=None):
        header = self.header_to_edit
        return super().get_match_formset(header)


class IndividualTransactionMixin:

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        pk = kwargs.get('pk')
        header = get_object_or_404(self.get_header_model(), pk=pk)
        self.header_to_edit = header

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["header_to_edit"] = self.header_to_edit
        context["edit"] = self.header_to_edit.pk
        return context


class RESTBaseEditTransactionMixin:

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        self.nom_trans = transaction_type_object.edit_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )

    def dispatch(self, request, *args, **kwargs):
        if self.header_to_edit.is_void():
            return HttpResponseForbidden("Void transactions cannot be edited")
        return super().dispatch(request, *args, **kwargs)

    def lines_are_valid(self):
        self.header_obj.save()
        self.header_has_been_saved = True
        self.line_formset.save(commit=False)
        self.lines_to_delete = self.line_formset.deleted_objects
        line_forms = self.line_formset.ordered_forms if self.lines_should_be_ordered(
        ) else self.line_formset
        lines_to_be_created_or_updated_only = []  # excluding those to delete
        for form in line_forms:
            if form.empty_permitted and form.has_changed():
                lines_to_be_created_or_updated_only.append(form)
            elif not form.empty_permitted and form.instance not in self.lines_to_delete:
                lines_to_be_created_or_updated_only.append(form)

        line_no = 1
        lines_to_update = []
        for form in lines_to_be_created_or_updated_only:
            if form.empty_permitted and form.has_changed():
                form.instance.header = self.header_obj
                form.instance.line_no = line_no
                line_no = line_no + 1
            elif not form.empty_permitted:
                if form.instance.is_non_zero():
                    form.instance.line_no = line_no
                    line_no = line_no + 1
                    lines_to_update.append(form.instance)
                else:
                    self.line_formset.deleted_objects.append(form.instance)

        self.lines_to_update = lines_to_update
        self.new_lines = new_lines = self.get_line_model(
        ).objects.bulk_create(self.line_formset.new_objects)
        self.get_line_model().objects.line_bulk_update(lines_to_update)
        self.get_line_model().objects.filter(
            pk__in=[line.pk for line in self.line_formset.deleted_objects]
        ).delete()

        if self.requires_analysis(self.header_form):
            existing_nom_trans = self.get_nominal_transaction_model(
            ).objects.filter(header=self.header_obj.pk)
            self.create_or_update_related_transactions(
                new_lines=new_lines,
                updated_lines=lines_to_update,
                deleted_lines=self.line_formset.deleted_objects,
                existing_nom_trans=existing_nom_trans
            )


class BaseEditTransaction(RESTBaseEditTransactionMixin,
                          RESTIndividualTransactionForHeaderMixin,
                          RESTIndividualTransactionMixin,
                          IndividualTransactionMixin,
                          BaseTransaction):

    def get_success_message(self):
        return "Transaction was edited successfully."

    def matching_is_valid(self):
        if not hasattr(self, 'header_has_been_saved'):
            self.header_obj.save()
        self.match_formset.save(commit=False)
        new_matches = filter(
            lambda o: True if o.value else False, self.match_formset.new_objects)
        self.get_match_model().objects.bulk_create(new_matches)
        changed_objects = [obj for obj,
                           _tuple in self.match_formset.changed_objects]
        # exclude zeros from update
        to_update = filter(
            lambda o: True if o.value else False, changed_objects)
        # delete the zero values
        to_delete = filter(
            lambda o: True if not o.value else False, changed_objects)
        self.get_match_model().objects.bulk_update(
            to_update,
            ['value']
        )
        self.get_match_model().objects.filter(
            pk__in=[o.pk for o in to_delete]).delete()
        self.get_header_model().objects.bulk_update(
            self.match_formset.headers,
            ['due', 'paid']
        )


class NominalTransactionsMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nom_trans = (
            self.get_nominal_transaction_model()
                .objects
                .select_related("nominal__name")
                .filter(header=self.header_to_edit.pk)
                .filter(module=self.get_module())
                .values("nominal__name")
                .annotate(total=Sum("value"))
        )
        context["nominal_transactions"] = nom_trans
        return context


class EditCashBookEntriesMixin(CreateCashBookEntriesMixin):

    def create_or_update_cash_book_transactions(self, **kwargs):
        self.transaction_type_object.edit_cash_book_entry(
            self.get_cash_book_transaction_model(),
            **kwargs
        )


class EditCashBookTransaction(EditCashBookEntriesMixin, NominalTransactionsMixin, BaseEditTransaction):
    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        transaction_type_object.edit_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )


class EditPurchaseOrSalesTransaction(
        MatchingMixin,
        EditCashBookEntriesMixin,
        NominalTransactionsMixin,
        BaseEditTransaction):

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "control_nominal_name": self.control_nominal_name,
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        transaction_type_object.edit_nominal_transactions(
            self.get_nominal_model(),
            self.get_nominal_transaction_model(),
            **kwargs
        )


class BaseViewTransaction(
        RESTIndividualTransactionForHeaderMixin,
        RESTIndividualTransactionMixin,
        IndividualTransactionMixin,
        BaseTransaction):

    def get_void_form_action(self):
        return self.void_form_action

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_void"] = self.header_to_edit.is_void()
        context["edit"] = False
        context["view"] = self.header_to_edit.pk
        context["void_form"] = self.void_form(
            self.get_header_model(),
            self.get_void_form_action(),
            prefix="void",
            initial={"id": self.header_to_edit.pk}
        )
        return context

    def post(self, request, *args, **kwargs):
        # read only view
        # what about on the fly payments though ?
        # like Xero does
        raise Http404("Read only view.  Use Edit transaction to make changes.")


class ViewTransactionOnLedgerOtherThanNominal(NominalTransactionsMixin, BaseViewTransaction):
    """
    On all ledgers other than the nominal ledger the user should like to see the nominal transactions
    for the transaction.  It is pointless on the NL because the lines show this already.
    """
    pass


def create_on_the_fly(**forms):
    """
    Rather than have a multiple views for all the different
    objects which can be created on the fly we have one
    """

    def view(request):
        if request.is_ajax() and request.method == "POST":
            form_name = request.POST.get("form")
            if form_name in forms:
                prefix = forms[form_name].get("prefix")
                form = forms[form_name]["form"](
                    data=request.POST, prefix=prefix)
                success = False
                if form.is_valid():
                    success = True
                    inst = form.save()
                    if 'serializer' in forms[form_name]:
                        result = forms[form_name]["serializer"](inst)
                    else:
                        result = {
                            'id': inst.id,
                            'text': str(inst)
                        }
                    data = {
                        'success': success,
                        'result': result
                    }
                    return JsonResponse(
                        data=data
                    )
                else:
                    ctx = {}
                    ctx.update(csrf(request))
                    form_html = render_crispy_form(form, context=ctx)
                    data = {
                        'success': success,
                        'result': {
                            'form_html': form_html
                        }
                    }
                    return JsonResponse(
                        data=data,
                        safe=False
                    )
            else:
                raise Http404("Form not found")
        else:
            raise Http404()

    return view


class BaseVoidTransaction(View):
    http_method_names = ['post']

    def get_success_url(self):
        return self.success_url

    def get_transaction_module(self):
        return self.module

    def get_nominal_transaction_model(self):
        return self.nominal_transaction_model

    def form_is_valid(self):
        self.success = True
        transaction_to_void = self.form.instance
        transaction_to_void.status = "v"
        headers_to_update = []
        headers_to_update.append(transaction_to_void)
        if matching_model := self.get_matching_model():
            matches = (
                matching_model
                .objects
                .filter(
                    Q(matched_to=transaction_to_void)
                    |
                    Q(matched_by=transaction_to_void)
                )
                .select_related("matched_to")
                .select_related("matched_by")
            )
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
            matching_model.objects.filter(
                pk__in=[match.pk for match in matches]
            ).delete()

        self.get_header_model().objects.bulk_update(
            headers_to_update,
            ["paid", "due", "status"]
        )
        # DO WE REALLY THIS?  MORE ELEGANT TO JUST DO WITHOUT
        if transaction_to_void.will_have_nominal_transactions():
            nom_trans = (
                self.get_nominal_transaction_model()
                .objects
                .filter(module=self.get_transaction_module())
                .filter(header=transaction_to_void.pk)
            ).delete()

    def form_is_invalid(self):
        self.success = False
        non_field_errors = self.form.non_field_errors()
        self.error_message = render_to_string(
            "messages.html", {"messages": [non_field_errors[0]]})

    def get_header_model(self):
        return self.header_model

    def get_matching_model(self):
        if hasattr(self, "matching_model"):
            return self.matching_model

    def get_form_prefix(self):
        return self.form_prefix

    def get_void_form_kwargs(self):
        return {
            "data": self.request.POST,
            "prefix": self.get_form_prefix()
        }

    def get_void_form(self):
        form_action = None  # does not matter for the form with this view
        return self.form(self.get_header_model(), form_action, **self.get_void_form_kwargs())

    def post(self, request, *args, **kwargs):
        self.form = form = self.get_void_form()
        if form.is_valid():
            self.form_is_valid()
            return JsonResponse(
                data={
                    "success": self.success,
                    "href": self.get_success_url()
                }
            )
        else:
            self.form_is_invalid()
            return JsonResponse(
                data={
                    "success": self.success,
                    "error_message": self.error_message
                }
            )


class DeleteCashBookTransMixin:

    def get_cash_book_transaction_model(self):
        return self.cash_book_transaction_model

    def form_is_valid(self):
        super().form_is_valid()
        transaction_to_void = self.form.instance
        cash_book_trans = (self.get_cash_book_transaction_model()
                           .objects
                           .filter(module=self.get_transaction_module())
                           .filter(header=transaction_to_void.pk)
                           ).delete()


class AgeDebtReportMixin(jQueryDataTable, TemplateResponseMixin, View):

    """

        CHALLENGE YOURSELF!

            This report does nearly all the work in Python i.e. it pulls out
            the data from the database and then applies filtering and ordering
            in Python.  It would be interesting to ee how much could be done
            in Postgresql directly as I'm pretty confident the ORM cannot
            be used further.

        Why do it in Python?

            Ordering cannot be applied at the SQL level since the values to be ordered -
            some at least - are not known when the query executes.  Only after another
            sql are we in a position to calculate these values.  Likewise, filtering
            cannot be applied either until the these values have been calculated.

        This is how we approach the problem -

            Get all the transactions out of the DB.  And all the matching transactions.

            We need to know the `recordsTotal`.  This assumes a valid form and is
            the total number of transactions the report would show without a
            supplier or customer filter.  The period filter cannot be dismissed
            because the report makes no sense otherwise.  Only group the
            transactions for each supplier if this is needed.

            We then apply the contact filtering.  Apply either to the individual
            transactions or the group set.  From this we get the `recordsFiltered`

            Next we need to order the transactions.  Again either the grouped
            or the grouped set.

            Finally we take the slice of the relevant set.

    """

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        if request.is_ajax():
            data = {}
            if 'form_html' not in context:
                data["success"] = True
                data["data"] = {
                    "draw": int(request.GET.get('draw'), 0),
                    "recordsTotal": context["recordsTotal"],
                    "recordsFiltered": context["recordsFiltered"],
                    "data": context["data"]
                }
            else:
                data["form_html"] = context["form_html"]
            data["data"] = {
                "draw": int(request.GET.get('draw'), 0),
                "recordsTotal": context["recordsTotal"],
                "recordsFiltered": context["recordsFiltered"],
                "data": context["data"]
            }
            return JsonResponse(data=data)
        else:
            return self.render_to_response(context)

    """

        I overlooked the following initially -

            Given that most of the report work i.e. filtering is done in Python
            I have to apply paginatation and count the records in Python also for
            the jQuery Datatables plugin.

    """

    def filter_by_contact(self, transactions, from_contact, to_contact):
        """
        `transactions` could be individual or the summary transaction for a supplier
        or customer
        """
        filtered_by_contact = []
        if from_contact or to_contact:
            for tran in transactions:
                contact_pk = tran["meta"]["contact_pk"]
                if from_contact and to_contact:
                    if contact_pk >= from_contact.pk and contact_pk <= to_contact.pk:
                        filtered_by_contact.append(tran)
                elif from_contact:
                    if contact_pk >= from_contact.pk:
                        filtered_by_contact.append(tran)
                elif to_contact:
                    if contact_pk <= to_contact.pk:
                        filtered_by_contact.append(tran)
            return filtered_by_contact
        return transactions

    def aggregate_is_zero(self, aggregate):
        if (
            aggregate["total"] or aggregate["unallocated"] or aggregate["current"]
            or aggregate["1 month"] or aggregate["2 month"] or aggregate["3 month"]
            or aggregate["4 month"]
        ):
            return False
        else:
            return True

    def create_report_transaction(self, header, report_period):
        """
        `header` e.g. PurchaseHeader or SaleHeader
        """
        report_tran = {
            "meta": {
                "contact_pk": header.supplier.pk
            },
            "supplier": header.supplier.name,
            "date": header.date,
            # JSONBlankDate just returns "" instead of the datetime when serialized.
            # we need this because otherwise the order_objects cannot work
            # i.e. str < date object will not work
            "due_date": header.due_date or JSONBlankDate(1900, 1, 1),
            "ref": header.ref,
            "total": header.total,
        }
        if header.is_payment_type():
            report_tran["unallocated"] = header.due
            report_tran["current"] = 0
            report_tran["1 month"] = 0
            report_tran["2 month"] = 0
            report_tran["3 month"] = 0
            report_tran["4 month"] = 0
        else:
            report_tran["unallocated"] = 0
            period = Period(report_period)
            if header.period == period:
                report_tran["current"] = header.due
            else:
                report_tran["current"] = 0
            if header.period == period - 1:
                report_tran["1 month"] = header.due
            else:
                report_tran["1 month"] = 0
            if header.period == period - 2:
                report_tran["2 month"] = header.due
            else:
                report_tran["2 month"] = 0
            if header.period == period - 3:
                report_tran["3 month"] = header.due
            else:
                report_tran["3 month"] = 0
            if header.period <= period - 4:
                report_tran["4 month"] = header.due
            else:
                report_tran["4 month"] = 0
        return report_tran

    def aggregate_transactions(self, transactions):
        def _aggregate_transactions(x, y):
            x["unallocated"] += y["unallocated"]
            x["total"] += y["total"]
            x["current"] += y["current"]
            x["1 month"] += y["1 month"]
            x["2 month"] += y["2 month"]
            x["3 month"] += y["3 month"]
            x["4 month"] += y["4 month"]
            return x
        return functools.reduce(_aggregate_transactions, transactions)

    def get_context_data(self, **kwargs):
        context = {}
        if self.request.is_ajax():
            # get the report
            form = self.get_filter_form()(data=self.request.GET)
            if form.is_valid():
                from_supplier = form.cleaned_data.get("from_supplier")
                to_supplier = form.cleaned_data.get("to_supplier")
                period = form.cleaned_data.get("period")
                start = int(self.request.GET.get("start", 0))
                length = int(self.request.GET.get("length", 25))
                queryset = (
                    self.get_transaction_queryset()
                    .filter(period__lte=period)
                    .order_by("supplier")
                )
                # FIX ME - rename `creditors` to 'unmatched_at_period' on the MODEL
                # This must preserve the ordering
                transactions = self.get_header_model().creditors(list(queryset), period)

                # get the recordsTotal for the response
                if form.cleaned_data.get("show_transactions"):
                    unfiltered_count = len(transactions)
                else:
                    suppliers_trans = groupby(
                        transactions, key=lambda t: t.supplier)
                    unfiltered_count = 0
                    aggregates = []
                    for supplier, trans in suppliers_trans:
                        report_trans = [
                            self.create_report_transaction(tran, period) 
                            for tran in trans
                        ]
                        aggregate = self.aggregate_transactions(report_trans)
                        if not self.aggregate_is_zero(aggregate):
                            unfiltered_count += 1
                            aggregates.append(aggregate)
                    aggregates = list(chain(aggregates))

                # filter by the supplier or customer.  This is the only true filter because
                # period is necessary for the report to make sense.  You cannot have a report
                # without a period.

                if form.cleaned_data.get("show_transactions"):
                    report_transactions = []
                    for tran in transactions:
                        report_transactions.append(
                            self.create_report_transaction(tran, period)
                        )
                    filtered_report_transactions = self.filter_by_contact(
                        report_transactions,
                        from_supplier,
                        to_supplier
                    )
                else:
                    filtered_report_transactions = self.filter_by_contact(
                        aggregates,
                        from_supplier,
                        to_supplier
                    )

                # get the recordsFiltered count
                filtered_count = len(filtered_report_transactions)
                report_transactions = self.order_objects(filtered_report_transactions)
                report_transactions = report_transactions[start:start + length]

                context["recordsTotal"] = unfiltered_count
                context["recordsFiltered"] = filtered_count
                context["data"] = report_transactions

            else:
                context["recordsTotal"] = 0
                context["recordsFiltered"] = 0
                context["data"] = []
                # i think because the form is get there is no csrf token
                ctx = {}
                ctx["form"] = form
                fields = ['from_supplier', 'to_supplier']
                for field in fields:
                    chosen = form.cleaned_data.get(field)
                    if chosen:
                        form.fields[field].widget.choices = [(chosen.pk, str(chosen))]
                form_html = render_to_string(
                    "purchases/creditors_form.html", ctx)
                context["form_html"] = form_html
        else:
            # page load -- render default filter form
            # no report is rendered because ajax request is made on page load
            # for the report
            form = self.get_filter_form()(
                initial={"period": "202007", "show_transactions": True})
            context["form"] = form
        return context


class LoadMatchingTransactions(jQueryDataTable, ListView):

    """
    Standard django pagination will not work here
    """

    def get_context_data(self, **kwargs):
        context = {}
        start = self.request.GET.get("start", 0)
        length = self.request.GET.get("length", 25)
        count = self.get_queryset().count()
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
        # https://datatables.net/manual/server-side#Example-data
        # total records, before filtering.  I.e. the total number
        # of records in the DB
        context["recordsTotal"] = count
        # Total records, after filtering i.e. the total number
        # of records after filtering has been applied - not just
        # the number of records being returned for this page
        context["recordsFiltered"] = count
        # this would be wrong if we searched !!!
        context["data"] = data

        # for matching transactions, when this was first built, there
        # is no optional filtering allowed so count is for before filtered
        # and total
        return context

    def get_header_model(self):
        return self.header_model

    def get_matching_model(self):
        return self.matching_model

    def get_contact_name(self):
        return self.contact_name

    def get_queryset(self):
        if contact := self.request.GET.get("s"):
            contact_name = self.get_contact_name()
            q = (
                self.get_header_model().objects
                .filter(**{contact_name: contact})
                .exclude(
                    due__exact=0)
                .order_by(*self.order_by())
            )
            if edit := self.request.GET.get("edit"):
                matches = (self.get_matching_model().objects
                           .filter(
                    Q(matched_to=edit) | Q(matched_by=edit)
                ))
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
            return self.get_header_model().objects.none()

    def render_to_response(self, context, **response_kwargs):
        data = {
            "draw": int(self.request.GET.get('draw'), 0),
            "recordsTotal": context["recordsTotal"],
            "recordsFiltered": context["recordsFiltered"],
            "data": context["data"]
        }
        return JsonResponse(data)


class LoadContacts(ListView):
    paginate_by = 50

    def get_contact_model(self):
        return self.model

    def get_queryset(self):
        if q := self.request.GET.get('q'):
            return (
                self.get_contact_model().objects.annotate(
                    similarity=TrigramSimilarity('code', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return self.get_contact_model().objects.none()

    def render_to_response(self, context, **response_kwargs):
        contacts = []
        for contact in context["page_obj"].object_list:
            s = {
                'code': contact.code,
                "id": contact.id
            }
            contacts.append(s)
        data = {"data": contacts}
        return JsonResponse(data)


def ajax_form_validator(forms):

    def func(request):
        success = False
        status = 404
        response_data = {}
        if form := request.GET.get("form"):
            data = request.GET
        elif form := request.POST.get("form"):
            data = request.POST

        if form in forms:
            form_instance = forms[form](data=data)
            status = 200
            if form_instance.is_valid():
                success = True
            else:
                ctx = {}
                ctx.update(csrf(request))
                form_html = render_crispy_form(form_instance, context=ctx)
                response_data.update({
                    "form_html": form_html
                })
        response_data.update({
            "success": success,
            "status": status
        })
        return JsonResponse(data=response_data, status=status)

    return func

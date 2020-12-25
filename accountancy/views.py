import functools
from copy import deepcopy
from datetime import date
from itertools import chain, groupby

from controls.exceptions import MissingPeriodError
from controls.models import Period
from crispy_forms.helper import FormHelper
from crispy_forms.utils import render_crispy_form
from django.conf import settings
from django.contrib import messages
from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import (Http404, HttpResponse, HttpResponseForbidden,
                         HttpResponseRedirect, JsonResponse)
from django.shortcuts import get_object_or_404, render, reverse
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.views.generic import DetailView, ListView, View
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from mptt.utils import get_cached_trees
from nominals.models import Nominal
from querystring_parser import parser

from accountancy.helpers import (AuditTransaction, JSONBlankDate,
                                 bulk_delete_with_history, sort_multiple)


def get_trig_vectors_for_different_inputs(model_attrs_and_inputs):
    """
    This builds a TrigramSimilarity search across many model attributes
    for the given search input.
    """
    trig_vectors = [
        TrigramSimilarity(model_attr, search_input)
        for model_attr, search_input in model_attrs_and_inputs
    ]
    return functools.reduce(lambda a, b: a + b, trig_vectors)


def get_value(obj, field):
    try:
        return getattr(obj, field)
    except AttributeError:
        return obj.get(field)


"""
Scroller and ScrollInView are used by the class which supports JQueryDataTable scroller i.e. JQueryDataTableScrollerMixin

JQueryDataTable scroller differs to normal pagination in that the slice will not necessarily, in fact rarely,
be the same slice as a page.  For example the slice could be from the middle of one page to the middle of the next.

paginate_by is a method which supports pagination and uses the Paginator class from django core.  It returns both an instance of
the paginator class and a page object which is just the object returned by calling a page number from the paginator object.  The paginator
object is used for getting the count of the whole filtered set; the page object contains the slice of objects which will be rendered on the UI.

The Scroller class below uses the same interface as the paginator class and the ScrollerInView class uses the same interface as
the page object class.  The second is necessary to take the slice we need and the first is necessary to return this object.

This way we can swap these classes for the paginator classes without changing the code.
"""


class ScrollerInView:
    def __init__(self, queryset_or_object_list, start, length):
        self.queryset_or_object_list = queryset_or_object_list
        self.start = start
        self.length = length

    @property
    def object_list(self):
        start = self.start
        length = self.length
        return self.queryset_or_object_list[int(start): int(start) + int(length)]


class Scroller:
    def __init__(self, queryset_or_object_list, start, length):
        if isinstance(queryset_or_object_list, (list,)):
            self.is_queryset = False
        else:
            self.is_queryset = True  # at least we expect a queryset
        self._q = queryset_or_object_list
        self.start = start
        self.length = length

    @property
    def queryset(self):
        if not self.is_queryset:
            raise AttributeError("Queryset was not passed to Scroller")
        return self._q.all()  # a new copy of the queryset object so original is not evaluated

    @property
    def queryset_or_object_list(self):
        if self.is_queryset:
            return self.queryset
        else:
            return self._q

    @property
    def count(self):
        if self.is_queryset:
            return self.queryset.count()
        else:
            return len(self._q)

    @property
    def visible(self):
        return ScrollerInView(self.queryset_or_object_list, self.start, self.length)


class JQueryDataTableMixin:
    """
    A mixin to help with implementing jQueryDataTables where the data is gotten via Ajax.
    """
    paginate_by = 25
    searchable_fields = None
    row_identifier = None

    def get(self, request, *args, **kwargs):
        if request.is_ajax():
            table_data = self.get_table_data()
            return JsonResponse(data=table_data, safe=False)
        return self.render_to_response(self.load_page())

    def apply_filter(self, queryset, **kwargs):
        parsed_request = parser.parse(self.request.GET.urlencode())
        if search_value := parsed_request["search"]["value"]:
            if self.searchable_fields:
                queryset = queryset.annotate(
                    similarity=(
                        get_trig_vectors_for_different_inputs([
                            (field, search_value, )
                            for field in self.searchable_fields
                        ])
                    )
                ).filter(similarity__gt=0.5)
        return queryset

    def get_row(self, obj):
        row = {}
        for column in self.columns:
            row[column] = getattr(obj, column)
        return row

    def get_row_href(self, obj):
        pass

    def get_queryset(self, **kwargs):
        return self.model.objects.all()

    def get_row_identifier(self, row):
        if self.row_identifier:
            return getattr(row, self.row_identifier)
        return row.pk

    def order(self, queryset):
        return queryset.order_by(*self.order_by())

    def queryset_count(self, queryset):
        q = queryset.all()  # creates a new queryset object
        # otherwise queryset argument is evaluated
        return q.count()

    def set_dt_row_data(self, obj, row):
        row["DT_RowData"] = {
            "pk": self.get_row_identifier(obj),
            "href": self.get_row_href(obj)
        }
        return row

    def get_table_data(self, **kwargs):
        queryset = self.get_queryset(**kwargs)
        # counts the set before filtering i.e. total
        queryset_count = self.queryset_count(queryset)
        queryset = self.apply_filter(queryset, **kwargs)
        queryset = self.order(queryset)
        paginator_object, page_object = self.paginate_objects(queryset)
        rows = []
        for obj in page_object.object_list:
            row = self.get_row(obj)
            row = self.set_dt_row_data(obj, row)
            rows.append(row)
        draw = int(self.request.GET.get("draw", 0))
        recordsTotal = queryset_count
        recordsFiltered = paginator_object.count  # counts the filtered set
        data = rows
        return {
            "draw": draw,
            "recordsTotal": recordsTotal,
            "recordsFiltered": recordsFiltered,
            "data": data
        }

    def load_page(self, **kwargs):
        return {}

    def paginate_objects(self, objects):
        """
        Only use this if you are using pagination.  It isn't suitable for jQuery scroller because the
        scroller will request slices which don't necessarily conform to the whole pages.  For this see the
        mixin class JQueryDataTableScrollMixin below.
        """
        start = self.request.GET.get("start", 0)
        paginate_by = self.request.GET.get("length", self.paginate_by)
        paginator_obj = Paginator(objects, paginate_by)
        page_number = int(int(start) / int(paginate_by)) + 1
        try:
            page_obj = paginator_obj.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator_obj.page(1)
        except EmptyPage:
            page_obj = paginator_obj.page(paginator_obj.num_pages)
        return paginator_obj, page_obj

    def order_objects(self, objs):
        """
        Sometimes it is not possible in Django to use the ORM, or it would be tricky,
        so we have to order in python.
        """
        orm_ordering = self.order_by()
        ordering = []
        for order in orm_ordering:
            if order[0] == "-":
                field = order[1:]
                desc = True
            else:
                field = order
                desc = False
            ordering.append(
                (lambda obj: get_value(obj, field), desc)
            )
        return sort_multiple(objs, *ordering)

    def order_by(self):
        ordering = []  # will pass this to ORM to order the fields correctly
        # create objects out of GET params
        # without this package the QueryDict object is tricky to use.  We just want a nested dict
        d = parser.parse(self.request.GET.urlencode())
        # which this package gives us.
        order = d.get("order")
        columns = d.get("columns")
        if order:
            for order_index, ordered_column in order.items():
                column_index = ordered_column.get("column")
                try:
                    column_index = int(column_index)
                    if column_index >= 0:
                        try:
                            column = columns[column_index]
                            field_name = column.get("data")
                            if field_name:
                                order_dir = ordered_column.get("dir")
                                if order_dir in ["asc", "desc"]:
                                    ordering.append(
                                        ("" if order_dir ==
                                         "asc" else "-") + field_name
                                    )
                        except IndexError as e:
                            break
                except:
                    break
        return ordering


class CustomFilterJQueryDataTableMixin:
    """
    By default jQuery Datatables supports filtering by a single search input field.
    Often times however we'll want to use our own form for filtering.

    The form is rendered on the client like the table data, via ajax.  So we must
    render the form in the view.
    """

    def get_table_data(self, **kwargs):
        """
        get table data and filter form
        """
        use_form = True if self.request.GET.get("use_adv_search") else False
        if use_form:
            form = self.get_filter_form(bind_form=True)
            kwargs.update({"form": form})
        else:
            form = self.get_filter_form()
        table_data = super().get_table_data(**kwargs)
        ctx = {}
        ctx.update(csrf(self.request))
        if hasattr(self, "form_template"):
            ctx["form"] = form
            form_html = render_to_string(
                self.form_template, ctx)
        else:
            form_html = render_crispy_form(form, context=ctx)
        table_data["form"] = form_html
        return table_data

    def get_filter_form_kwargs(self, **kwargs):
        form_kwargs = {}
        if kwargs.get("bind_form"):
            kwargs.pop("bind_form")
            kwargs.update({"data": self.request.GET})
        form_kwargs.update(kwargs)
        return form_kwargs

    def get_filter_form(self, **kwargs):
        return self.filter_form_class(
            **self.get_filter_form_kwargs(**kwargs)
        )

    def apply_filter(self, queryset, **kwargs):
        if form := kwargs.get("form"):
            if form.is_valid():
                queryset = self.filter_form_valid(queryset, form)
            else:
                queryset = self.filter_form_invalid(queryset, form)
        return queryset

    def filter_form_valid(self, queryset, form):
        return queryset

    def filter_form_invalid(self, queryset, form):
        return queryset


class JQueryDataTableScrollerMixin:
    """
    Supports the scroller feature of jQueryDataTables.
    """

    def paginate_objects(self, queryset_or_object_list):
        start = self.request.GET.get("start", 0)
        length = self.request.GET.get("length", 25)
        s = Scroller(queryset_or_object_list, start, length)
        return s, s.visible


class SalesAndPurchaseSearchMixin:
    def apply_advanced_search(self, queryset, cleaned_data):
        reference = cleaned_data.get("reference")
        total = cleaned_data.get("total")
        period = cleaned_data.get("period")
        search_within = cleaned_data.get("search_within")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        include_voided = cleaned_data.get("include_voided")
        if reference:
            queryset = (
                queryset.annotate(
                    similarity=(
                        get_trig_vectors_for_different_inputs(
                            self.get_list_of_search_values_for_model_attrs(
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
        if not include_voided:
            queryset = queryset.exclude(status="v")
        return queryset


class NominalSearchMixin:
    def apply_advanced_search(self, queryset, cleaned_data):
        reference = cleaned_data.get("reference")
        total = cleaned_data.get("total")
        period = cleaned_data.get("period")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if reference:
            queryset = (
                queryset.annotate(
                    similarity=(
                        get_trig_vectors_for_different_inputs(
                            self.get_list_of_search_values_for_model_attrs(
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
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        return queryset


class BaseTransactionsList(CustomFilterJQueryDataTableMixin,
                           JQueryDataTableMixin,
                           TemplateResponseMixin,
                           View):
    column_transformers = {}
    # keys are those fields you want to show form,
    form_field_to_searchable_model_attr = {}
    # values are those model attrs the form field maps to

    def get_list_of_search_values_for_model_attrs(self, form_cleaned_data):
        """
        Will be used for Trigram Search
        """
        return [
            (model_attr, form_cleaned_data.get(form_field, ""))
            for form_field, model_attr in self.form_field_to_searchable_model_attr.items()
        ]

    def load_page(self, **kwargs):
        context_data = {}
        context_data["columns"] = [field[0] for field in self.fields]
        context_data["column_labels"] = [field[1] for field in self.fields]
        return context_data

    def get_row(self, obj):
        for column, transformer in self.column_transformers.items():
            obj[column] = transformer(obj[column])
        return obj

    def filter_form_valid(self, queryset, form):
        return self.apply_advanced_search(queryset, form.cleaned_data)

    def get_row_identifier(self, row):
        if self.row_identifier:
            return row[self.row_identifier]
        return row["id"]


class SalesAndPurchasesTransList(SalesAndPurchaseSearchMixin, BaseTransactionsList):
    pass


class CashBookAndNominalTransList(NominalSearchMixin, BaseTransactionsList):
    pass


class RESTBaseTransactionMixin:

    def create_or_update_related_transactions(self, **kwargs):
        self.create_or_update_nominal_transactions(**kwargs)
        self.create_or_update_vat_transactions(**kwargs)

    def get_transaction_type_object(self):
        if hasattr(self, "transaction_type_object"):
            return self.transaction_type_object
        else:
            self.transaction_type_object = self.header_obj.get_type_transaction()
            return self.transaction_type_object

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
        t = None
        if hasattr(header_form, "cleaned_data"):
            t = header_form.cleaned_data.get("type")
        else:
            t = self.header_form.initial.get('type')
        if t:
            if t in self.get_header_model().get_types_requiring_analysis():
                return True
        return False

    def get_header_model(self):
        return self.header.get('model')

    def requires_lines(self, header_form):
        t = None
        if hasattr(header_form, "cleaned_data"):
            t = header_form.cleaned_data.get("type")
        else:
            t = self.header_form.initial.get('type')
        if t:
            if t in self.get_header_model().get_types_requiring_lines():
                return True
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
        # a flag used for UI rendering e.g. hide the nominal column
        kwargs["brought_forward"] = brought_forward
        # and to decide whether the field is required server side
        return kwargs

    def get_line_formset(self, header=None):
        if hasattr(self, 'line'):
            if hasattr(self, 'line_formset'):
                return self.line_formset
            else:
                formset_class = self.line.get('formset')
                return formset_class(**self.get_line_formset_kwargs(header))

    def lines_are_invalid(self):
        self.line_formset = self.get_line_formset()
        if self.line_formset:
            self.line_formset.is_valid()
            # validation will not run again if this method has already been run
            # see is_valid method at - https://github.com/django/django/blob/master/django/forms/forms.py
            if self.line_formset.non_form_errors():
                self.non_field_errors = True
            for form in self.line_formset:
                if form.non_field_errors():
                    self.non_field_errors = True

    def header_is_invalid(self):
        if self.header_form.non_field_errors():
            self.non_field_errors = True

    def invalid_forms(self):
        self.forms_invalid = True
        self.header_is_invalid()
        if self.requires_lines(self.get_header_form()):
            self.lines_are_invalid()
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        self.header_form = self.get_header_form()
        if self.header_form.is_valid():
            self.header_obj = self.header_form.save(commit=False)
            self.line_formset = self.get_line_formset(self.header_obj)
            if self.line_formset.is_valid():
                self.header_obj.save()
                self.lines_are_valid()
            else:
                return self.invalid_forms()
        else:
            return self.invalid_forms()
        return self.get_successful_response()


class BaseTransaction(
        RESTBaseTransactionMixin,
        TemplateResponseMixin,
        ContextMixin,
        View):

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

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
        if 'header_form' not in kwargs:
            kwargs["header_form"] = self.get_header_form()
        if 'header_prefix' not in kwargs:
            kwargs['header_form_prefix'] = self.get_header_prefix()
        if self.requires_lines(kwargs["header_form"]):
            if 'line_form_prefix' not in kwargs:
                kwargs["line_form_prefix"] = self.get_line_prefix()
            if 'line_formset' not in kwargs:
                kwargs["line_formset"] = self.get_line_formset()
        if 'forms_invalid' not in kwargs:
            if hasattr(self, 'forms_invalid'):
                kwargs['forms_invalid'] = self.forms_invalid
        if 'non_field_errors' not in kwargs:
            if hasattr(self, 'non_field_errors'):
                kwargs['non_field_errors'] = self.non_field_errors
        if 'negative_transaction_types' not in kwargs:
            # calculator.js needs this
            kwargs['negative_transaction_types'] = self.get_header_model().negatives
        if hasattr(self, 'create_on_the_fly'):
            for form in self.create_on_the_fly:
                kwargs[form] = self.create_on_the_fly[form]
        return super().get_context_data(**kwargs)

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())


class RESTBaseCreateTransactionMixin:
    permission_action = 'create'

    def get_default_type(self):
        return self.default_type

    def get_header_form_type(self):
        return self.request.GET.get("t", self.get_default_type())

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        transaction_type_object = self.get_transaction_type_object()
        self.nom_trans = transaction_type_object.create_nominal_transactions(
            self.nominal_model,
            self.nominal_transaction_model,
            **kwargs
        )

    def create_or_update_vat_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
        })
        transaction_type_object = self.get_transaction_type_object()
        self.vat_trans = transaction_type_object.create_vat_transactions(
            self.vat_transaction_model,
            **kwargs
        )

    def lines_are_valid(self):
        line_no = 1
        lines = []
        line_forms = self.line_formset.ordered_forms if self.lines_should_be_ordered(
        ) else self.line_formset
        for form in line_forms:
            if form.empty_permitted and form.has_changed():
                line = form.save(commit=False)
                line.header = self.header_obj
                line.type = self.header_obj.type
                line.line_no = line_no
                lines.append(line)
                line_no = line_no + 1
        if lines:
            self.lines = self.get_line_model().objects.audited_bulk_create(lines)
            self.create_or_update_related_transactions(lines=lines)

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if self.request.method in ('GET'):
            kwargs["initial"] = {
                "type": self.get_header_form_type()
            }
        return kwargs


class BaseCreateTransaction(
        RESTBaseCreateTransactionMixin,
        BaseTransaction):

    def get_success_message(self):
        return "Transaction was created successfully."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["create"] = True  # some javascript templates depend on this
        context["header_type"] = self.get_header_form_type()
        return context


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
    pass


class BaseMatchingMixin:
    matching_formset_template = "accounts/whole_uni_formset.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["match_formset"] = self.get_match_formset()
        context["match_form_prefix"] = self.get_match_prefix()
        return context

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
                f = formset_class(**self.get_match_formset_kwargs(header))
                f.helper = FormHelper()
                f.helper.template = self.matching_formset_template
                return f

    def matching_is_invalid(self):
        self.match_formset = self.get_match_formset()
        if self.match_formset:
            self.match_formset.is_valid()
            if self.match_formset.non_form_errors():
                self.non_field_errors = True
            for form in self.match_formset:
                if form.non_field_errors():
                    self.non_field_errors = True

    def invalid_forms(self):
        self.matching_is_invalid()
        return super().invalid_forms()

    def post(self, request, *args, **kwargs):
        self.header_form = self.get_header_form()
        if self.header_form.is_valid():
            self.header_obj = self.header_form.save(commit=False)
            self.line_formset = self.get_line_formset(self.header_obj)
            self.match_formset = self.get_match_formset(self.header_obj)
            if not self.requires_lines(self.header_form):
                if self.match_formset.is_valid():
                    self.header_obj.save()
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
                        self.header_obj.save()
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


class CreateMatchingMixin(BaseMatchingMixin):

    def matching_is_valid(self):
        matches = []
        for form in self.match_formset:
            if form.empty_permitted and form.has_changed():
                match = form.save(commit=False)
                match.matched_by_type = match.matched_by.type
                match.matched_to_type = match.matched_to.type
                match.period = self.header_obj.period
                if match.value != 0:
                    matches.append(match)
        if matches:
            self.get_header_model().objects.audited_bulk_update(
                self.match_formset.headers,
                ['due', 'paid']
            )
            self.get_match_model().objects.audited_bulk_create(matches)


class CreatePurchaseOrSalesTransaction(
        CreateMatchingMixin,
        CreateCashBookEntriesMixin,
        BaseCreateTransaction):

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "control_nominal_name": self.control_nominal_name,
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        # e.g. Invoice, CreditNote etc
        transaction_type_object = self.get_transaction_type_object()
        transaction_type_object.create_nominal_transactions(
            self.nominal_model,
            self.nominal_transaction_model,
            **kwargs
        )


class RESTIndividualTransactionForHeaderMixin:
    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if not hasattr(self, 'main_header'):
            raise AttributeError(
                f"{self.__class__.__name__} has no 'main_header' attribute.  Did you override "
                "setup() and forget to class super()?"
            )
        kwargs["instance"] = self.main_header
        return kwargs


class RESTIndividualTransactionMixin:

    def get_line_formset_kwargs(self, header=None):
        kwargs = super().get_line_formset_kwargs(header)
        if not header:
            kwargs["header"] = self.main_header
        return kwargs

    def get_line_formset_queryset(self):
        return self.get_line_model().objects.filter(header=self.main_header)

class IndividualTransactionMixin:

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        pk = kwargs.get('pk')
        header = get_object_or_404(self.get_header_model(), pk=pk)
        self.main_header = header

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["main_header"] = self.main_header
        context["edit"] = self.main_header.pk
        return context


class RESTBaseEditTransactionMixin:
    permission_action = 'edit'

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        transaction_type_object = self.get_transaction_type_object()
        self.nom_trans = transaction_type_object.edit_nominal_transactions(
            self.nominal_model,
            self.nominal_transaction_model,
            **kwargs
        )

    def create_or_update_vat_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
        })
        transaction_type_object = self.get_transaction_type_object()
        self.vat_trans = transaction_type_object.edit_vat_transactions(
            self.vat_transaction_model,
            **kwargs
        )

    def dispatch(self, request, *args, **kwargs):
        if self.main_header.is_void():
            return HttpResponseForbidden("Void transactions cannot be edited")
        return super().dispatch(request, *args, **kwargs)

    def lines_are_valid(self):
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
                form.instance.type = self.header_obj.type
                line_no = line_no + 1
            elif not form.empty_permitted:
                if form.instance.is_non_zero():
                    form.instance.line_no = line_no
                    form.instance.type = self.header_obj.type
                    line_no = line_no + 1
                    lines_to_update.append(form.instance)
                else:
                    self.line_formset.deleted_objects.append(form.instance)
        self.lines_to_update = lines_to_update
        self.new_lines = new_lines = self.get_line_model(
        ).objects.audited_bulk_create(self.line_formset.new_objects)
        self.get_line_model().objects.audited_bulk_update(lines_to_update)
        bulk_delete_with_history(
            self.line_formset.deleted_objects,
            self.get_line_model()
        )
        if self.requires_analysis(self.header_form):
            existing_nom_trans = self.nominal_transaction_model.objects.filter(
                module=self.module,
                header=self.header_obj.pk)
            existing_vat_trans = self.vat_transaction_model.objects.filter(
                module=self.module, header=self.header_obj.pk)
            self.create_or_update_related_transactions(
                new_lines=new_lines,
                lines_to_update=lines_to_update,
                deleted_lines=self.line_formset.deleted_objects,
                existing_nom_trans=existing_nom_trans,
                existing_vat_trans=existing_vat_trans
            )


class ViewTransactionAuditMixin:
    def get_audit(self):
        header = self.main_header
        audit = AuditTransaction(
            header,
            self.get_header_model(),
            self.get_line_model()
        )
        return audit.get_historical_changes()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["audits"] = self.get_audit()
        context["multi_object_audit"] = True
        return context


class BaseEditTransaction(RESTBaseEditTransactionMixin,
                          RESTIndividualTransactionForHeaderMixin,
                          RESTIndividualTransactionMixin,
                          IndividualTransactionMixin,
                          ViewTransactionAuditMixin,
                          BaseTransaction):

    def get_success_message(self):
        return "Transaction was edited successfully."

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["edit_mode"] = "1"  # js script interpretes this as truthy
        return context_data


class EditMatchingMixin(CreateMatchingMixin):
    matching_formset_template = "accounts/edit_matching_formset.html"

    def get_match_formset_queryset(self):
        return (
            self.get_match_model()
            .objects
            .filter(Q(matched_by=self.main_header) | Q(matched_to=self.main_header))
            .select_related('matched_by')
            .select_related('matched_to')
        )

    def get_match_formset(self, header=None):
        header = self.main_header
        return super().get_match_formset(header)

    def matching_is_valid(self):
        self.match_formset.save(commit=False)
        to_create = [
            m.instance
            for m in self.match_formset
            if not m.instance.pk and m.instance.value
        ]
        to_update = [
            m.instance
            for m in self.match_formset
            if m.instance.pk and m.instance.value
        ]
        to_delete = [
            m.instance
            for m in self.match_formset
            if m.instance.pk and not m.instance.value
        ]
        for match in to_create + to_update:
            if match.matched_by_id == self.header_obj.pk:
                match.matched_by_type = self.header_obj.type
                match.matched_to_type = match.matched_to.type
                match.period = self.header_obj.period
            else:
                match.matched_by_type = match.matched_by.type
                match.matched_to_type = self.header_obj.type
        self.get_match_model().objects.audited_bulk_create(to_create)
        self.get_match_model().objects.audited_bulk_update(
            to_update, ['value', 'matched_by_type', 'matched_to_type', 'period'])
        bulk_delete_with_history(
            to_delete,
            self.get_match_model()
        )
        self.get_header_model().objects.audited_bulk_update(
            self.match_formset.headers,
            ['due', 'paid']
        )


class NominalTransactionsMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nom_trans = (
            self.nominal_transaction_model
                .objects
                .select_related("nominal__name")
                .filter(header=self.main_header.pk)
                .filter(module=self.module)
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


class EditCashBookTransaction(
        EditCashBookEntriesMixin,
        NominalTransactionsMixin,
        BaseEditTransaction):
    pass


class ViewSaleOrPurchaseTransactionAuditMixin:
    def get_audit(self):
        header = self.main_header
        audit = AuditTransaction(
            header,
            self.get_header_model(),
            self.get_line_model(),
            self.get_match_model()
        )
        return audit.get_historical_changes()


class EditPurchaseOrSalesTransaction(
        EditCashBookEntriesMixin,
        NominalTransactionsMixin,
        EditMatchingMixin,
        ViewSaleOrPurchaseTransactionAuditMixin,
        BaseEditTransaction):

    def create_or_update_nominal_transactions(self, **kwargs):
        kwargs.update({
            "line_cls": self.get_line_model(),
            "control_nominal_name": self.control_nominal_name,
            "vat_nominal_name": settings.DEFAULT_VAT_NOMINAL,
        })
        transaction_type_object = self.get_transaction_type_object()
        transaction_type_object.edit_nominal_transactions(
            self.nominal_model,
            self.nominal_transaction_model,
            **kwargs
        )


class BaseViewTransaction(
    ViewTransactionAuditMixin,
    DetailView):
    """
    No REST BASE exists for view yet.  Remember to move permission_action
    to this class when it is created
    """
    permission_action = 'view'
    context_object_name = "header"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.main_header = self.object = self.get_object()  # need this before dispatch for
        # TransactionPermissionMixin

    def get(self, request, *args, **kwargs):
        # self.object = self.get_object().  Set in setup instead.  See above.
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_header_model(self):
        return self.model

    def get_line_model(self):
        return self.line_model

    def get_void_form_kwargs(self, header):
        return {
            "prefix": "void",
            "initial": {"id": header.pk}
        }

    def get_void_form(self, header=None):
        return self.void_form(
            self.model,
            self.get_void_form_action(header=header),
            **self.get_void_form_kwargs(header=header)
        )

    def get_void_form_action(self, header):
        return reverse(self.void_form_action, kwargs={"pk": header.pk})

    def get_edit_view_name(self):
        return self.edit_view_name

    def get_context_data(self, **kwargs):
        self.main_header = header = self.object
        context = super().get_context_data(**kwargs)
        context["lines"] = lines = self.line_model.objects.select_related(
            "header").filter(header=header)
        context["void_form"] = self.get_void_form(header=header)
        context["module"] = self.module
        context["edit_view_name"] = self.get_edit_view_name()
        context["edit_mode"] = ""  # js script interprets this as a Falsey
        return context


class MatchingViewTransactionMixin:

    def get_match_model(self):
        return self.match_model

    def get_context_data(self, **kwargs):
        self.main_header = header = self.object
        context = super().get_context_data(**kwargs)
        matches = (
            self.match_model
            .objects
            .select_related("matched_by")
            .select_related("matched_to")
            .filter(
                Q(matched_by=header) | Q(matched_to=header)
            )
        )
        match_objs = []
        for match in matches:
            if match.matched_by_id == header.pk:
                match_obj = {
                    "type": match.matched_to.get_type_display(),
                    "ref": match.matched_to.ref,
                    "total": match.matched_to.ui_total,
                    "paid": match.matched_to.ui_paid,
                    "due": match.matched_to.ui_due,
                    "value": match.ui_match_value(match.matched_to, match.value)
                }
            else:
                match_obj = {
                    "type": match.matched_by.get_type_display(),
                    "ref": match.matched_by.ref,
                    "total": match.matched_by.ui_total,
                    "paid": match.matched_by.ui_paid,
                    "due": match.matched_by.ui_due,
                    "value": match.ui_match_value(match.matched_by, -1 * match.value)
                }
            match_objs.append(match_obj)
        context["matches"] = match_objs
        return context


class SaleAndPurchaseViewTransaction(
        NominalTransactionsMixin,
        MatchingViewTransactionMixin,
        ViewSaleOrPurchaseTransactionAuditMixin,
        BaseViewTransaction):
    pass


class BaseVoidTransaction(
    IndividualTransactionMixin, 
    View):
    http_method_names = ['post']
    permission_action = "void"

    def get_success_url(self):
        return self.success_url

    def update_headers(self):
        self.header_model.objects.audited_bulk_update(
            self.headers_to_update,
            ["paid", "due", "status"]
        )

    def delete_related(self):
        (
            self.nominal_transaction_model
            .objects
            .filter(module=self.module)
            .filter(header=self.transaction_to_void.pk)
            .delete()
        )
        (
            self.vat_transaction_model
            .objects
            .filter(module=self.module)
            .filter(header=self.transaction_to_void.pk)
            .delete()
        )

    def form_is_valid(self):
        self.success = True
        self.transaction_to_void = self.form.instance
        self.transaction_to_void.status = "v"
        self.headers_to_update = [self.transaction_to_void]
        self.update_headers()
        self.delete_related()

    def form_is_invalid(self):
        self.success = False
        non_field_errors = self.form.non_field_errors()
        self.error_message = render_to_string(
            "messages.html", {"messages": [non_field_errors[0]]})

    def get_header_model(self):
        # we do not need this for the void views
        # but other mixins rely on this
        # TODO - remove these unpythonic getters
        return self.header_model

    def get_form_prefix(self):
        return self.form_prefix

    def get_void_form_kwargs(self):
        return {
            "data": self.request.POST,
            "prefix": self.get_form_prefix()
        }

    def get_void_form(self):
        form_action = None  # does not matter for the form with this view
        return self.form(self.header_model, form_action, **self.get_void_form_kwargs())

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


class SaleAndPurchaseVoidTransaction(BaseVoidTransaction):
    
    def get_void_form_kwargs(self):
        kwargs = super().get_void_form_kwargs()
        kwargs.update({
            "matching_model": self.matching_model
        })
        return kwargs

    def form_is_valid(self):
        self.success = True
        self.transaction_to_void = self.form.instance
        self.transaction_to_void.status = "v"
        self.headers_to_update = [self.transaction_to_void]
        matches = self.form.matches
        matching_model = self.matching_model
        for match in matches:
            if match.matched_by_id == self.transaction_to_void.pk:
                # value is the amount of the matched_to transaction that was matched
                # e.g. transaction_to_void is 120.00 payment and matched to 120.00 invoice
                # value = 120.00
                self.transaction_to_void.paid += match.value
                self.transaction_to_void.due -= match.value
                match.matched_to.paid -= match.value
                match.matched_to.due += match.value
                self.headers_to_update.append(match.matched_to)
            else:
                # value is the amount of the transaction_to_void which was matched
                # matched_by is an invoice for 120.00 and matched_to is a payment for 120.00
                # value is -120.00
                self.transaction_to_void.paid -= match.value
                self.transaction_to_void.due += match.value
                match.matched_by.paid += match.value
                match.matched_by.due -= match.value
                self.headers_to_update.append(match.matched_by)
        bulk_delete_with_history(
            matches,
            matching_model
        )
        self.update_headers()
        self.delete_related()




class DeleteCashBookTransMixin:

    def delete_related(self):
        super().delete_related()
        transaction_to_void = self.form.instance
        (
            self.cash_book_transaction_model
            .objects
            .filter(module=self.module)
            .filter(header=self.transaction_to_void.pk)
            .delete()
        )





class AgeMatchingReportMixin(
        JQueryDataTableScrollerMixin,
        CustomFilterJQueryDataTableMixin,
        JQueryDataTableMixin,
        TemplateResponseMixin,
        View):
    show_trans_columns = [
        # add the subclasses' contact_field_name here
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
    column_transformers = {
        "date": lambda d: d.strftime('%d %b %Y') if d and not isinstance(d, JSONBlankDate) else "",
        # payment trans do not have due dates
        "due_date": lambda d: d.strftime('%d %b %Y') if d and not isinstance(d, JSONBlankDate) else ""
    }

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
        # header e.g. PurchaseHeader or SaleHeader
        contact_field_name = self.contact_field_name
        report_tran = {
            "meta": {
                "contact_pk": getattr(header, contact_field_name).pk
            },
            contact_field_name: getattr(header, contact_field_name).name,
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

            if header.period == report_period:
                report_tran["current"] = header.due
            else:
                report_tran["current"] = 0

            try:
                if header.period == report_period - 1:
                    report_tran["1 month"] = header.due
                else:
                    report_tran["1 month"] = 0
            except MissingPeriodError:
                report_tran["1 month"] = 0

            try:
                if header.period == report_period - 2:
                    report_tran["2 month"] = header.due
                else:
                    report_tran["2 month"] = 0
            except MissingPeriodError:
                report_tran["2 month"] = 0

            try:
                if header.period == report_period - 3:
                    report_tran["3 month"] = header.due
                else:
                    report_tran["3 month"] = 0
            except MissingPeriodError:
                report_tran["3 month"] = 0

            try:
                if header.period <= report_period - 4:
                    report_tran["4 month"] = header.due
                else:
                    report_tran["4 month"] = 0
            except MissingPeriodError:
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
        aggregate = functools.reduce(_aggregate_transactions, transactions)
        aggregate["ref"] = ''
        aggregate["date"] = ''
        aggregate["due_date"] = ''
        return aggregate

    def load_page(self):
        context = {}
        current_period = Period.objects.first() 
        # obviously this will need to look up the current period of the PL or SL eventually
        form = self.get_filter_form(
            initial={"period": current_period, "show_transactions": True})
        context["form"] = form
        context["columns"] = columns = []
        show_trans_columns = self.show_trans_columns.copy()
        show_trans_columns.insert(0, self.contact_field_name)
        for column in show_trans_columns:
            if type(column) is type(""):
                columns.append({
                    "label": column.title(),
                    "field": column
                })
            elif isinstance(column, dict):
                columns.append(column)
        from_contact_field, to_contact_field = self.get_contact_range_field_names()
        context["contact_field_name"] = self.contact_field_name
        context["from_contact_field"] = from_contact_field
        context["to_contact_field"] = to_contact_field
        return context

    def get_contact_range_field_names(self):
        return self.contact_range_field_names

    def get_row_identifier(self, obj):
        return

    def get_row(self, obj):
        for column, transformer in self.column_transformers.items():
            obj[column] = transformer(obj[column])
        return obj

    def queryset_count(self, filtered_and_ordered_transactions):
        return len(filtered_and_ordered_transactions)

    def order(self, filtered_transactions):
        return self.order_objects(filtered_transactions)

    def filter_form_valid(self, transactions, form):
        from_contact_field, to_contact_field = self.get_contact_range_field_names()
        from_contact = form.cleaned_data.get(from_contact_field)
        to_contact = form.cleaned_data.get(to_contact_field)
        period = form.cleaned_data.get("period")
        # only filter applied so far is `period` but for the purpose of recordsFiltered which jQueryDataTable needs,
        # this does not count because it is a necessary filter
        # now we filter by the contact below.  This does count and so it is the first real filter (i.e. optional)
        if form.cleaned_data.get("show_transactions"):
            report_trans = []
            for tran in transactions:
                report_trans.append(
                    self.create_report_transaction(tran, period)
                )
        else:
            report_trans = transactions
        return self.filter_by_contact(report_trans, from_contact, to_contact)

    def filter_form_invalid(self, queryset, form):
        return []

    def get_queryset(self, **kwargs):
        q = super().get_queryset(**kwargs)
        queryset = q.select_related(self.contact_field_name)
        form = kwargs["form"]
        if not form.is_valid():
            return []
        contact_field_name = self.contact_field_name
        from_contact_field, to_contact_field = self.get_contact_range_field_names()
        from_contact = form.cleaned_data.get(from_contact_field)
        to_contact = form.cleaned_data.get(to_contact_field)
        period = form.cleaned_data.get("period")
        # queryset is simply the whole set of PL or SL transactions
        queryset = queryset.exclude(status="v").filter(period__lte=period).order_by(
            contact_field_name)  # must order in case
        # we need to group by contact_field_name below
        transactions = self.match_model.get_not_fully_matched_at_period(
            list(queryset), period)
        if not form.cleaned_data.get("show_transactions"):
            contact_trans = groupby(
                transactions, key=lambda t: getattr(t, self.contact_field_name))
            aggregates = []
            for contact, trans in contact_trans:
                report_trans = [
                    self.create_report_transaction(tran, period)
                    for tran in trans
                ]
                aggregate = self.aggregate_transactions(report_trans)
                if not self.aggregate_is_zero(aggregate):
                    aggregates.append(aggregate)
            aggregates = list(chain(aggregates))
            return aggregates
        return transactions


class LoadMatchingTransactions(
        JQueryDataTableScrollerMixin,
        JQueryDataTableMixin,
        TemplateResponseMixin,
        View):

    def set_dt_row_data(self, obj, row):
        row["DT_RowData"] = {
            "pk": self.get_row_identifier(obj),
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
                    'value': obj.ui_total,
                    'order': obj.ui_total
                },
                "paid": {
                    'value': obj.ui_paid,
                    'order': obj.ui_paid
                },
                "due": {
                    'value': obj.ui_due,
                    'order': obj.ui_due
                },
                "matched_to": {
                    'value': obj.pk,
                    'order': obj.pk
                }
            }
        }
        return row

    def get_row(self, obj):
        return {
            "type": {
                "label": obj.get_type_display(),
                "value": obj.type
            },
            "ref": obj.ref,
            "total": obj.ui_total,
            "paid": obj.ui_paid,
            "due": obj.ui_due
        }

    def apply_filter(self, queryset, **kwargs):
        if contact := self.request.GET.get("s"):
            contact_name = self.contact_name
            queryset = (
                queryset
                .filter(**{contact_name: contact})
                .exclude(due__exact=0)
                .exclude(status="v")
            )
            if edit := self.request.GET.get("edit"):
                matches = (
                    self.match_model.objects.filter(
                        Q(matched_to=edit) | Q(matched_by=edit))
                )
                matches = [(match.matched_by_id, match.matched_to_id)
                           for match in matches]
                matched_headers = list(chain(*matches))
                pk_to_exclude = [header for header in matched_headers]
                # at least exclude the record being edited itself !!!
                pk_to_exclude.append(edit)
                queryset = queryset.exclude(pk__in=pk_to_exclude)
        else:
            queryset = queryset.none()
        return queryset


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

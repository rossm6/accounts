import functools
from copy import deepcopy

from django.contrib.postgres.search import SearchVector
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.generic import ListView
from querystring_parser import parser

from .widgets import InputDropDown


def get_search_vectors(searchable_fields):
    search_vectors = [
        SearchVector(field)
        for field in searchable_fields
    ]
    return functools.reduce(lambda a, b: a + b, search_vectors)


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


class BaseTransactionsList(ListView):
    # model = Transaction -- subclass implements
    # fields = [
    #     ('supplier__name', 'Supplier'), 
    #     ('ref1', 'Reference 1'),
    #     ('date', 'Date'),
    #     ('due_date', 'Due date'),
    #     ('paid', 'Paid'),
    #     ('due', 'Due'),
    #     ('status', 'Status')
    # ] ( actual db field name, label for UI )
    # template_name = "accounting/transactions.html"
    # advanced_search_form_class -- subclass implements
    # searchable_fields = ['supplier__name', 'ref1', 'total'] -- subclass implements
    # datetime_fields = ['date', 'due_date'] -- subclass implements
    # datetime_format = '%d %b %Y' -- subclass implements

    def order_by(self):
        ordering = [] # will pass this to ORM to order the fields correctly
        d = parser.parse(self.request.GET.urlencode()) # create objects out of GET params
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
                                    ( "" if order_by == "asc" else "-") + field_name
                                )
                    except IndexError as e:
                        break
        return ordering

    # at the moment we assume these fields exist
    # but may want to make this configurable at later stage
    def apply_advanced_search(self, cleaned_data):
        search = cleaned_data.get("search")
        search_within = cleaned_data.get("search_within")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        queryset = self.get_queryset()
        if search:
            queryset = (
                queryset.annotate(
                        search=get_search_vectors(self.searchable_fields)
                    )
                    .filter(search=search)
            )
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

    # defined on the parent class in case the subclass doesn't
    # care about providing a url to the transaction
    # but often times this will surely be implemented by the subclass
    def get_transaction_url(self, **kwargs):
        pass

    def get_context_data(self, **kwargs):
        context_data = {}
        context_data["columns"] = [ field[0] for field in self.fields]
        context_data["column_labels"] = [ field[1] for field in self.fields ]
        if self.request.is_ajax() and self.request.method == "GET" and self.request.GET.get('use_adv_search'):
            form = self.advanced_search_form_class(data=self.request.GET)
            # form = AdvancedTransactionSearchForm(data=self.request.GET)
            # This form was not validating despite a valid datetime being entered on the client
            # The problem was jquery.serialize encodes
            # And on top of this jQuery datatable does also
            # solution on client - do not use jQuery.serialize
            if form.is_valid():
                queryset = self.apply_advanced_search(form.cleaned_data)
            else:
                queryset = self.get_queryset()
        else:
            # context_data["form"] = AdvancedTransactionSearchForm()
            context_data["form"] = self.advanced_search_form_class()
            queryset = self.get_queryset()
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
        for col in page_obj.object_list:
            col["DT_RowData"] = {
                "pk": col["id"],
                "href": self.get_transaction_url(pk=col["id"])
            }
            rows.append(col)
        format_dates(rows, self.datetime_fields, self.datetime_format)
        context_data["data"] = rows
        return context_data
        
    # Example -
    # subclass implements this
    # def get_queryset(self):
    #     return (
    #         Transaction.objects
    #         .select_related('supplier')
    #         .all()
    #         .values(
    #             'id',
    #             *self.fields
    #         )
    #         .order_by(*self.order_by())
    #     )

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
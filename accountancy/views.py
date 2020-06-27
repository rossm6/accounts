import functools
from copy import deepcopy

from django.contrib import messages
from django.contrib.postgres.search import SearchVector
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import (Http404, HttpResponse, HttpResponseRedirect,
                         JsonResponse)
from django.shortcuts import render, reverse
from django.views.generic import ListView, View
from django.views.generic.base import ContextMixin, TemplateResponseMixin
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





# E.G USAGE -

# class CreatePurchaseTransactions(CreateTransactions):
#     header = {
#         model: PurchaseHeader,
#         form: PaymentForm,
#         prefix: 'header'
#     }
#     line = {
#         model: PurchaseLine,
#         form: PurchaseLineForm,
#         formset: PurchaseLineFormSet
#     }
#     match = {
#         model: PurchaseMatching,
#         form: PurchaseMatchingForm,
#         formset: PurchaseMatchingFormset
#     }

class BaseCreateTransaction(TemplateResponseMixin, ContextMixin, View):

    def get_context_data(self, **kwargs):
        # FIX ME - change 'matching_formset" to "match_formset" in the template
        if 'header_form' not in kwargs:
            kwargs["header_form"] = self.get_header_form()
        if 'line_formset' not in kwargs:
            kwargs["line_formset"] = self.get_line_formset()
        if 'matching_formset' not in kwargs:
            kwargs["matching_formset"] = self.get_match_formset()
        if 'header_prefix' not in kwargs:
            kwargs['header_form_prefix'] = self.get_header_prefix()
        if 'line_form_prefix' not in kwargs:
            kwargs["line_form_prefix"] = self.get_line_prefix()
        if 'matching_form_prefix' not in kwargs:
            kwargs["matching_form_prefix"] = self.get_match_prefix()
        if 'non_field_errors' not in kwargs:
            if hasattr(self, 'non_field_errors'):
                kwargs['non_field_errors'] = self.non_field_errors
        if 'payment_form' not in kwargs:
            kwargs['payment_form'] = self.is_payment_form()
        return super().get_context_data(**kwargs)


    def override_choices(self):
        """
        Will override the specified choices so that only the instance of the form being
        validated remains.  Necessary as some choices may contain thousands of items which
        will take ages to render using django crispy forms.
        """
        # override choices is a list.  May need to provide a dictionary eventually
        # with a function as the value to use for setting the choices
        for choice in self.header.get('override_choices'):
            chosen = self.header_form.cleaned_data.get(choice)
            if chosen:
                field = self.header_form.fields[choice]
                field.widget.choices = [ (chosen.pk, str(chosen)) ] # will do for now
        
        if self.line_formset:
            if override_choices := self.line.get('override_choices'):
                for form in self.line_formset:
                    for choice in override_choices:
                        field = form.fields[choice]
                        if chosen := form.cleaned_data.get(choice):
                            field.widget.choices = [ (chosen.pk, str(chosen)) ]
                        else:
                            field.widget.choices = []

        # Shoudn't be any need to do this for match_formset
        # I recommend you override the select input widget for a text input to prevent
        # all choices rendering


    def invalid_forms(self):

        """
        This gets all the errors possible from the forms.
        """

        # make sure all non field errors are generated
        # at form and formset level
        # we also set a flag to true only because this helps
        # the template rendering
        if self.header_form.non_field_errors():
            self.non_field_errors = True
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
        self.match_formset = self.get_match_formset()
        if self.match_formset:
            self.match_formset.is_valid()
            if self.match_formset.non_form_errors():
                self.non_field_errors = True
            for form in self.match_formset:
                if form.non_field_errors():
                    self.non_field_errors = True

        # choices for some forms could contain thousands of items
        # this will take django crispy forms way too long to render
        # so we offer the choice to override the choices so it includes
        # only the selected item
        self.override_choices()

        return self.render_to_response(self.get_context_data())
        

    def lines_are_valid(self):
        line_no = 0
        lines = []
        self.header_obj.save() # this could have been updated by line formset clean method already
        for form in self.line_formset.ordered_forms:
            if form.empty_permitted and form.has_changed():
                line_no = line_no + 1
                line = form.save(commit=False)
                line.header = self.header_obj
                line.line_no = line_no
                lines.append(line)
        if lines:
            self.get_line_model().objects.bulk_create(lines)

    def matching_is_valid(self):
        self.header_obj.save()
        matches = []
        for form in self.match_formset:
            if form.empty_permitted and form.has_changed():
                match = form.save(commit=False)
                matches.append(match)
        if matches:
            self.get_header_model().objects.bulk_update(
                self.match_formset.headers,
                ['due', 'paid']
            )
            self.get_match_model().objects.bulk_create(matches)

    def get_header_model(self):
        return self.header.get('model')

    def get_line_model(self):
        return self.line.get('model')

    def get_match_model(self):
        return self.match.get('model')

    def get_header_form_initial(self):
        initial = self.header.get('initial', {})
        if t := self.request.GET.get("t", "i"):
            initial["type"] = t
        return initial

    def get_header_prefix(self):
        return self.header.get('prefix', 'header')

    def get_line_prefix(self):
        if hasattr(self, 'line'):
            return self.line.get('prefix', 'line')

    def get_match_prefix(self):
        if hasattr(self, 'match'):
            return self.match.get('prefix', 'match')

    def get_header_form_kwargs(self):
        kwargs = {
            'prefix': self.get_header_prefix()
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
            })
        elif self.request.method in ('GET'):
            # IMPORTANT THIS IS ONLY SET ON GET
            kwargs.update({
                'initial': self.get_header_form_initial()
            })
        
        return kwargs

    def get_line_formset_kwargs(self, header=None):
        kwargs = {
            'prefix': self.get_line_prefix(),
            'queryset': self.get_line_model().objects.none()
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
                'header': header
            })
        
        return kwargs

    def get_match_formset_kwargs(self, header=None):
        kwargs = {
            'prefix': self.get_match_prefix(),
            'queryset': self.get_match_model().objects.none()
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
                'match_by': header
            })
        
        return kwargs

    def is_payment_form(self):
        if self.header_form.initial["type"] in ("bp", "p", "br", "r"):
            return True
        else:
            return False

    def get_header_form(self):
        if hasattr(self, "header_form"):
            return self.header_form
        form_class = self.header.get('form')
        self.header_form = form_class(**self.get_header_form_kwargs())
        return self.header_form
        
    def get_line_formset(self, header=None):
        if hasattr(self, 'line'):
            if hasattr(self, 'line_formset'):
                return self.line_formset
            else:
                formset_class = self.line.get('formset')
                return formset_class(**self.get_line_formset_kwargs(header))

    def get_match_formset(self, header=None):
        if hasattr(self, 'match'):
            if hasattr(self, 'match_formset'):
                return self.match_formset
            else:
                formset_class = self.match.get('formset')
                return formset_class(**self.get_match_formset_kwargs(header))

    def get(self, request, *args, **kwargs):
        """ Handle GET requests: instantiate a blank version of the form. """
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate forms with the passed POST variables
        and then check if it is valid

        WARNING - LINE FORMSET MUST BE VALIDATED BEFORE MATCH FORMSET

        """
        self.header_form = self.get_header_form()
        if self.header_form.is_valid():
            self.header_obj = self.header_form.save(commit=False) # changed name from header because this is a cls attribute of course
            self.line_formset = self.get_line_formset(self.header_obj)
            self.match_formset = self.get_match_formset(self.header_obj)
            if self.header_obj.type in ('bp', 'p', 'br', 'r'):
                # e.g. processing payments on PL
                if self.match_formset.is_valid():
                    self.matching_is_valid()
                    messages.success(
                        request,
                        'Transaction successfully created' # may want to change this
                    )
                else:
                    return self.invalid_forms()
            else:
                # e.g. processing invoice on PL
                if self.line_formset.is_valid() and self.match_formset.is_valid():
                    self.lines_are_valid() # has to come before matching_is_valid because this formset could alter header_obj
                    self.matching_is_valid()
                    messages.success(
                        request,
                        'Transaction successfully created'
                    )
                else:
                    return self.invalid_forms()
            # other scenarios to consider later on ...
        else:
            return self.invalid_forms()

        # So we were successful
        return HttpResponseRedirect(reverse("purchases:create")) # FIX ME - get url from get_success_url()
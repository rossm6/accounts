import functools
from copy import deepcopy

from crispy_forms.utils import render_crispy_form
from django.conf import settings
from django.contrib import messages
from django.contrib.postgres.search import (SearchQuery, SearchRank,
                                            SearchVector, TrigramSimilarity)
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import (Http404, HttpResponse, HttpResponseRedirect,
                         JsonResponse)
from django.shortcuts import get_object_or_404, render, reverse
from django.template.context_processors import csrf
from django.views.generic import ListView, View
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from querystring_parser import parser

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




class jQueryDataTable(object):

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


class BaseTransactionsList(jQueryDataTable, ListView):
    
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



class BaseTransaction(TemplateResponseMixin, ContextMixin, View):

    def get_success_url(self):
        if creation_type := self.request.POST.get('approve'):
            if creation_type == "add_another":
                return self.request.get_full_path() # the relative path including the GET parameters e.g. /purchases/create?t=i
        return self.success_url

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
        if 'requires_analysis' not in kwargs:
            kwargs['requires_analysis'] = self.requires_analysis(kwargs["header_form"]) # as self.header_form not set for GET requests
        
        if hasattr(self, 'create_on_the_fly'):
            for form in self.create_on_the_fly:
                kwargs[form] = self.create_on_the_fly[form] # this is a form instance already

        return super().get_context_data(**kwargs)

    def invalid_forms(self):
        self.header_is_invalid()
        if self.requires_analysis(self.get_header_form()):
            self.lines_are_invalid()
        self.matching_is_invalid()
        return self.render_to_response(self.get_context_data())
        
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
                            field.widget.choices = [ (chosen.pk, str(chosen)) ]
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
                    field.widget.choices = [ (chosen.pk, str(chosen)) ]
                else:
                    field.widget.choices = []

    def lines_are_valid(self):
        line_no = 1
        lines = []
        self.header_obj.save() # this could have been updated by line formset clean method already
        self.header_has_been_saved = True
        line_forms = self.line_formset.ordered_forms if self.lines_should_be_ordered() else self.line_formset
        for form in line_forms:
            if form.empty_permitted and form.has_changed():
                line = form.save(commit=False)
                line.header = self.header_obj
                line.line_no = line_no
                lines.append(line)
                line_no = line_no + 1
        if lines:
            lines = self.get_line_model().objects.bulk_create(lines)
            # need the vat nominal for those lines which have vat values
            name_of_vat_nominal = settings.DEFAULT_VAT_NOMINAL
            try:
                vat_nominal = Nominal.objects.get(name=name_of_vat_nominal)
            except Nominal.DoesNotExist:
                vat_nominal = Nominal.objects.get(name=settings.DEFAULT_SYSTEM_SUSPENSE) # bult into system so cannot not exist
            nominal_transactions = []
            for line in lines:
                nominal_transactions += self.create_nominal_transaction(self.header_obj, line, vat_nominal)     
            if nominal_transactions:
                nominal_transactions = self.get_nominal_model().objects.bulk_create(nominal_transactions)
                # THIS IS CRAZILY INEFFICIENT !!!!
                for line in lines:
                    line_nominal_trans = {
                        nominal_transaction.field : nominal_transaction
                        for nominal_transaction in nominal_transactions 
                        if nominal_transaction.line == line.pk 
                    }
                    line.add_nominal_transactions(line_nominal_trans)
                self.get_line_model().objects.bulk_update(lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])

    def matching_is_valid(self):
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

    def get_header_model(self):
        return self.header.get('model')

    def get_line_model(self):
        return self.line.get('model')

    def get_match_model(self):
        return self.match.get('model')

    def get_nominal_model(self):
        return self.nominal_model

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
        
        return kwargs

    def get_line_formset_queryset(self):
        return self.get_line_model().objects.none()

    def get_line_formset_kwargs(self, header=None):
        kwargs = {
            'prefix': self.get_line_prefix(),
            'queryset': self.get_line_formset_queryset()
        }

        if self.request.method in ('POST', 'PUT'):
            # passing in data will mean the form will use the POST queryset
            # which means potentially huge choices rendered on the client
            if self.requires_analysis(self.header_form):
                kwargs.update({
                    'data': self.request.POST
                })
            kwargs.update({
                'header': header
            })
        
        return kwargs

    def lines_should_be_ordered(self):
        if hasattr(self, "line"):
            return self.line.get("can_order", True)

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

    
    # MIGHT BE OBSOLETE NOW
    def header_is_payment_type(self):
        return self.header_obj.type in ("pbp", "pp", "pbr", "pr")

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
            if not self.requires_analysis(self.header_form):
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
                if self.line_formset and self.match_formset:
                    if self.line_formset.is_valid() and self.match_formset.is_valid():
                        self.lines_are_valid() # has to come before matching_is_valid because this formset could alter header_obj
                        self.matching_is_valid()
                        messages.success(
                            request,
                            'Transaction successfully created'
                        )
                    else:
                        return self.invalid_forms()
                elif self.line_formset and not self.match_formset:
                    if self.line_formset.is_valid():
                        self.lines_are_valid()
                        messages.success(
                            request,
                            'Transaction successfully created'
                        )
                    else:
                        return self.invalid_forms()
        else:
            return self.invalid_forms()

        return HttpResponseRedirect(self.get_success_url())


class BaseCreateTransaction(BaseTransaction):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["create"] = True # some javascript templates depend on this
        return context

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if self.request.method in ('GET'):
            kwargs["initial"] = {
                "type": self.get_header_form_type()
            }
        return kwargs

    def create_nominal_transaction(self, header, line, vat_nominal):
        # LATER ON FIELDS OTHER THAN GOODS AND VAT MAY BE CREATED
        # LIKE DISCOUNT AND RETENTION
        trans = []
        trans.append(
            self.get_nominal_model()(
                module=self.module,
                header=header.pk,
                line=line.pk,
                nominal=line.nominal,
                value=line.goods,
                ref=header.ref,
                period=header.period,
                date=header.date,
                type=header.type,
                field="g"
            )
        )
        if line.vat != 0:
            trans.append(
                self.get_nominal_model()(
                    module=self.module,
                    header=header.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    type=header.type,
                    field="v"
                )
            )
        return trans

class BaseEditTransaction(BaseTransaction):

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        pk = kwargs.get('pk')
        header = get_object_or_404(self.get_header_model(), pk=pk)
        self.header_to_edit = header
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit"] = self.header_to_edit.pk
        return context

    def lines_are_valid(self):
        line_no = 1
        self.header_obj.save() # this could have been updated by line formset clean method already
        self.header_has_been_saved = True
        self.line_formset.save(commit=False)
        lines_to_delete = [ line.pk for line in self.line_formset.deleted_objects ]
        forms = []
        for form in self.line_formset.ordered_forms:
            if form.empty_permitted and form.has_changed():
                forms.append(form)
            elif not form.empty_permitted and form.instance.pk not in lines_to_delete:
                forms.append(form)
        updated = []
        for form in forms:
            if form.empty_permitted and form.has_changed():
                form.instance.header = self.header_obj
                form.instance.line_no = line_no
                line_no = line_no + 1
            elif not form.empty_permitted:
                form.instance.line_no = line_no
                updated.append(form.instance)
                line_no = line_no + 1
        self.get_line_model().objects.bulk_create(self.line_formset.new_objects)
        # FIXED.  I was updating the objects in changed_objects but this is no good
        # because i'm changing the line_no always
        self.get_line_model().objects.bulk_update(
            updated,
            ['line_no', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat']
        )
        self.get_line_model().objects.filter(pk__in=lines_to_delete).delete()

    def matching_is_valid(self):
        if not hasattr(self, 'header_has_been_saved'):
            self.header_obj.save()
        self.match_formset.save(commit=False)
        new_matches = filter(lambda o: True if o.value else False, self.match_formset.new_objects)
        self.get_match_model().objects.bulk_create(new_matches)
        changed_objects = [ obj for obj, _tuple in self.match_formset.changed_objects ]
        # exclude zeros from update
        to_update = filter(lambda o: True if o.value else False, changed_objects)
        # delete the zero values
        to_delete = filter(lambda o: True if not o.value else False, changed_objects)
        self.get_match_model().objects.bulk_update(
            to_update,
            [ 'value' ]
        )
        self.get_match_model().objects.filter(pk__in=[ o.pk for o in to_delete ]).delete()
        self.get_header_model().objects.bulk_update(
            self.match_formset.headers,
            ['due', 'paid']
        )

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

    def get_header_form_kwargs(self):
        kwargs = super().get_header_form_kwargs()
        if not hasattr(self, 'header_to_edit'):
            raise AttributeError(
                f"{self.__class__.__name__} has no 'header_to_edit' attribute.  Did you override "
                "setup() and forget to class super()?"
            )
        kwargs["instance"] = self.header_to_edit
        return kwargs


class BaseViewTransaction(BaseEditTransaction):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit"] = False
        context["view"] = self.header_to_edit.pk
        context["void_form"] = self.void_form(prefix="void", initial={"id": self.header_to_edit.pk})
        return context    

    def post(self, request, *args, **kwargs):
        # read only view
        # what about on the fly payments though ?
        # like Xero does
        raise Http404("Read only view.  Use Edit transaction to make changes.")


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
                form = forms[form_name]["form"](data=request.POST, prefix=prefix)
                success = False
                if form.is_valid():
                    success = True
                    inst = form.save()
                    if 'serializer' in forms[form_name]:
                        data=forms[form_name]["serializer"](inst)
                    else:
                        data = {
                            'success': success,
                            'result': {
                                'id': inst.id,
                                'text': str(inst)
                            }
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

import collections
from json import loads

from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from drf_yasg.inspectors import SwaggerAutoSchema
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.views import APIView, exception_handler

from accountancy.forms import (BaseVoidTransactionForm,
                               NominalTransactionSearchForm)
from accountancy.views import (BaseCreateTransaction, BaseEditTransaction,
                               BaseViewTransaction, BaseVoidTransaction,
                               NominalTransList,
                               RESTBaseCreateTransactionMixin,
                               RESTBaseEditTransactionMixin,
                               RESTBaseTransactionMixin,
                               RESTIndividualTransactionMixin,
                               create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)
from nominals.serializers import NominalHeaderSerializer, NominalLineSerializer
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import (NominalForm, NominalHeaderForm, NominalLineForm,
                    ReadOnlyNominalHeaderForm, ReadOnlyNominalLineForm,
                    enter_lines, read_only_lines)
from .models import Nominal, NominalHeader, NominalLine, NominalTransaction
from .serializers import NominalSerializer, NominalTransactionSerializer


class CreateTransaction(BaseCreateTransaction):
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header",
        "initial": {"total": 0},
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "override_choices": ["nominal"],  # VAT would not work at the moment
        "can_order": False
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("nominals:create_on_the_fly"), prefix="vat")
    }
    template_name = "nominals/create.html"
    success_url = reverse_lazy("nominals:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "NL"

    def get_header_form_type(self):
        t = self.request.GET.get("t", "nj")
        return t


class EditTransaction(BaseEditTransaction):
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header"
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "override_choices": ["nominal"],  # VAT would not work at the moment
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
        "can_order": False
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("nominals:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("nominals:create_on_the_fly"), prefix="vat")
    }
    template_name = "nominals/edit.html"
    success_url = reverse_lazy("nominals:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    module = "NL"


class ViewTransaction(BaseViewTransaction):
    header = {
        "model": NominalHeader,
        "form": ReadOnlyNominalHeaderForm,
        "prefix": "header",
    }
    line = {
        "model": NominalLine,
        "formset": read_only_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    void_form_action = reverse_lazy("nominals:void")
    void_form = BaseVoidTransactionForm
    template_name = "nominals/view.html"
    module = 'NL'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit_view_name"] = "nominals:edit"
        return context


load_options = input_dropdown_widget_load_options_factory(
    NominalLineForm(), 25)

validate_choice = input_dropdown_widget_validate_choice_factory(
    NominalLineForm())

create_on_the_fly_view = create_on_the_fly(
    nominal={
        "form": NominalForm,
        "prefix": "nominal"
    },
    vat={
        "form": QuickVatForm,
        "serializer": vat_object_for_input_dropdown_widget,
        "prefix": "vat"
    }
)


class TransactionEnquiry(NominalTransList):
    model = NominalTransaction
    # ORDER OF FIELDS HERE IS IMPORTANT FOR GROUPING THE SQL QUERY
    # ATM -
    # GROUP BY MODULE, HEADER, NOMINAL__NAME, PERIOD
    fields = [
        ("module", "Module"),
        ("header", "Internal Ref"),
        ("ref", "Ref"),
        ("nominal__name", "Nominal"),
        ("period", "Period"),
        ("date", "Date"),
        ("total", "Total"),
    ]
    form_field_to_searchable_model_field = {
        "nominal": "nominal__name",
        "reference": "ref"
    }
    datetime_fields = ["created", ]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = NominalTransactionSearchForm
    template_name = "nominals/transactions.html"
    row_identifier = "header"

    def get_transaction_url(self, **kwargs):
        row = kwargs.pop("row")
        module = row.get("module")
        header = row.get("header")
        modules = settings.ACCOUNTANCY_MODULES
        module_name = modules[module]
        return reverse_lazy(module_name + ":view", kwargs={"pk": header})

    def get_queryset(self):
        return (
            NominalTransaction.objects
            .select_related('nominal__name')
            .all()
            .values(
                *[field[0] for field in self.fields[:-1]]
            )
            .annotate(total=Sum("value"))
            .order_by(*self.order_by())
        )


class VoidTransaction(BaseVoidTransaction):
    header_model = NominalHeader
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("nominals:transaction_enquiry")
    module = 'NL'


"""

REST API VIEWS

Use the OpenAPI schema and this python client for making requests to the API -

    https://github.com/triaxtec/openapi-python-client 

"""


@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'nominals': reverse('nominals:nominal-list', request=request, format=format),
    })


class CustomSwaggerSchema(SwaggerAutoSchema):
    def add_manual_parameters(self, parameters):
        print(parameters)
        p = super().add_manual_parameters(parameters)
        return p


class NominalList(generics.ListCreateAPIView):
    queryset = Nominal.objects.all()
    serializer_class = NominalSerializer


class NominalDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Nominal.objects.all()
    serializer_class = NominalSerializer
    swagger_schema = CustomSwaggerSchema

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

# TODO - Create a mixin for the shared class attributes
# Create an EDIT, READ AND LIST FOR THE NOMINAL JOURNALS


class CreateNominalJournal(
        RESTBaseCreateTransactionMixin,
        RESTBaseTransactionMixin,
        APIView):
    """
    Inspired by this SO answer - https://stackoverflow.com/questions/35485085/multiple-models-in-django-rest-framework
    """
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header",
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "can_order": False
    }
    module = 'NL'
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    forms = ['header_form']
    formsets = ['line_formset']

    def get_successful_response(self):
        data = {}
        data["header"] = NominalHeaderSerializer(self.header_obj).data
        data["lines"] = NominalLineSerializer(self.lines, many=True).data
        data["nom_trans"] = NominalTransactionSerializer(
            self.nom_trans, many=True).data
        return JsonResponse(data=data)

    def invalid_forms(self):
        errors = {}
        for form in self.forms:
            if hasattr(self, form):
                form_instance = getattr(self, form)
                if not form_instance.is_valid():
                    json_str = form_instance.errors.as_json()
                    errors.update(
                        loads(json_str)
                    )
        for formset in self.formsets:
            if hasattr(self, formset):
                formset_instance = getattr(self, formset)
                if formset_instance.non_form_errors():
                    json_str = formset_instance.non_form_errors().as_json()
                    non_form_errors = loads(json_str)
                    for error in non_form_errors:
                        errors.update(error)
                for form_errors in formset_instance.errors:
                    json_str = form_errors.as_json()
                    errors.update(
                        loads(json_str)
                    )
        return JsonResponse(data=errors, status=HTTP_400_BAD_REQUEST)


class EditNominalJournal(
        RESTBaseEditTransactionMixin,
        RESTIndividualTransactionMixin,
        RESTBaseTransactionMixin,
        APIView):
    """
    Inspired by this SO answer - https://stackoverflow.com/questions/35485085/multiple-models-in-django-rest-framework
    """
    header = {
        "model": NominalHeader,
        "form": NominalHeaderForm,
        "prefix": "header",
    }
    line = {
        "model": NominalLine,
        "formset": enter_lines,
        "prefix": "line",
        "can_order": False
    }
    module = 'NL'
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    # This isn't that nice
    forms = ['header_form']
    formsets = ['line_formset']

    # use set up from accountancy generic views to set header_to_edit

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        pk = self.kwargs.get('pk')
        header = get_object_or_404(self.get_header_model(), pk=pk)
        self.header_to_edit = header

    def get_successful_response(self):
        data = {}
        data["header"] = NominalHeaderSerializer(self.header_obj).data
        lines = self.new_lines + self.lines_to_update
        lines.sort(key=lambda l: l.pk)
        data["lines"] = NominalLineSerializer(lines, many=True).data
        data["nom_trans"] = NominalTransactionSerializer(
            self.nom_trans, many=True).data
        return JsonResponse(data=data)

    def invalid_forms(self):
        errors = {}
        for form in self.forms:
            if hasattr(self, form):
                form_instance = getattr(self, form)
                if not form_instance.is_valid():
                    json_str = form_instance.errors.as_json()
                    errors.update(
                        loads(json_str)
                    )
        for formset in self.formsets:
            if hasattr(self, formset):
                formset_instance = getattr(self, formset)
                if formset_instance.non_form_errors():
                    json_str = formset_instance.non_form_errors().as_json()
                    errors.update(
                        loads(json_str)
                    )
                for form_errors in formset_instance.errors:
                    json_str = form_errors.as_json()
                    errors.update(
                        loads(json_str)
                    )
        return JsonResponse(data=errors, status=HTTP_400_BAD_REQUEST)


"""

    Example json output for form validation errors below.  this differs
    to what rest does.  https://www.django-rest-framework.org/api-guide/exceptions/ 

    {'ref': [{'message': 'This field is required.', 'code': 'required'}], 
    'date': [{'message': 'This field is required.', 'code': 'required'}], 
    'type': [{'message': 'This field is required.', 'code': 'required'}], 
    'period': [{'message': 'This field is required.', 'code': 'required'}]}

"""

# https://medium.com/@ratrosy/building-apis-with-openapi-ac3c24e33ee3


class JournalDetail(generics.RetrieveAPIView):
    queryset = NominalHeader.objects.all()

    def get(self, request, *args, **kwargs):
        pass


class NominalTransactionList(generics.ListAPIView):
    queryset = NominalTransaction.objects.all()
    serializer_class = NominalTransactionSerializer


class NominalTransactionDetail(generics.RetrieveAPIView):
    queryset = NominalTransaction.objects.all()
    serializer_class = NominalTransactionSerializer

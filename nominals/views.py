from json import loads

from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
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
                               RESTBaseTransactionMixin, create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)
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
"""


@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'nominals': reverse('nominals:nominal-list', request=request, format=format),
    })


class NominalList(generics.ListCreateAPIView):
    queryset = Nominal.objects.all()
    serializer_class = NominalSerializer


class NominalDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Nominal.objects.all()
    serializer_class = NominalSerializer


class NominalTransactionList(generics.ListAPIView):
    queryset = NominalTransaction.objects.all()
    serializer_class = NominalTransactionSerializer


class NominalTransactionDetail(generics.RetrieveAPIView):
    queryset = NominalTransaction.objects.all()
    serializer_class = NominalTransactionSerializer


# TODO - Create a mixin for the shared class attributes
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
    forms = [ 'header_form', 'line_form' ]

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
        return JsonResponse(data=errors, status=HTTP_400_BAD_REQUEST)


"""

    Example json output for form validation errors below.  this differs
    to what rest does.  https://www.django-rest-framework.org/api-guide/exceptions/ 

    {'ref': [{'message': 'This field is required.', 'code': 'required'}], 
    'date': [{'message': 'This field is required.', 'code': 'required'}], 
    'type': [{'message': 'This field is required.', 'code': 'required'}], 
    'period': [{'message': 'This field is required.', 'code': 'required'}]}

"""

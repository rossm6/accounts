from django.conf import settings
from django.db.models import Sum
from django.urls import reverse_lazy

from accountancy.forms import AdvancedTransactionSearchForm
from accountancy.views import (BaseCreateTransaction, BaseEditTransaction,
                               BaseTransactionsList, create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import NominalForm, NominalHeaderForm, NominalLineForm, enter_lines
from .models import Nominal, NominalHeader, NominalLine, NominalTransaction


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
        "override_choices": ["nominal"], # VAT would not work at the moment
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
        "override_choices": ["nominal"], # VAT would not work at the moment
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


load_options = input_dropdown_widget_load_options_factory(NominalLineForm(), 25)

validate_choice = input_dropdown_widget_validate_choice_factory(NominalLineForm())

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

class TransactionEnquiry(BaseTransactionsList):
    model = NominalTransaction
    # ORDER OF FIELDS HERE IS IMPORTANT FOR GROUPING THE SQL QUERY
    # ATM -
    # GROUP BY MODULE, HEADER, NOMINAL__NAME, PERIOD
    fields = [
        ("module", "Module"),
        ("header", "Unique Ref"),
        ("nominal__name", "Nominal"),
        ("period", "Period"),
        ("total", "Total"),
    ]
    searchable_fields = ["nominal__name", "ref", "value"]
    datetime_fields = ["created",]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = AdvancedTransactionSearchForm
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
                *[ field[0] for field in self.fields[:-1] ]
            )
            .annotate(total=Sum("value"))
            .order_by(*self.order_by())
        )

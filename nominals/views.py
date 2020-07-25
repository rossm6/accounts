from django.urls import reverse_lazy

from accountancy.forms import AdvancedTransactionSearchForm
from accountancy.views import (BaseCreateTransaction, BaseTransactionsList,
                               create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)
from nominals.forms import NominalHeaderForm, NominalLineForm, enter_lines
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import NominalForm
from .models import NominalHeader, NominalLine, NominalTransaction


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
    nominal_model = NominalTransaction
    module = "NL"    

    def get_header_form_type(self):
        t = self.request.GET.get("t", "nj")
        return t


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
    fields = [
        ("nominal__name", "Nominal"),
        ("period", "Period"),
        ("created", "Date"),
        ("value", "Value"),
    ]
    searchable_fields = ["nominal__name", "ref", "value"]
    datetime_fields = ["created",]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = AdvancedTransactionSearchForm
    template_name = "nominals/transactions.html"

    def get_transaction_url(self, **kwargs):
        pk = kwargs.pop("pk")
        return reverse_lazy("purchases:view", kwargs={"pk": pk})

    def get_queryset(self):
        return (
            NominalTransactions.objects
            .select_related('nominal__name')
            .all()
            .values(
                'id',
                *[ field[0] for field in self.fields ]
            )
            .order_by(*self.order_by())
        )
from django.db.models import Sum
from django.urls import reverse_lazy

from accountancy.forms import (BaseVoidTransactionForm,
                               CashBookTransactionSearchForm)
from accountancy.views import (BaseVoidTransaction, CreateCashBookTransaction,
                               EditCashBookTransaction, NominalTransList,
                               ViewTransactionOnLedgerOtherThanNominal,
                               create_on_the_fly,
                               input_dropdown_widget_load_options_factory,
                               input_dropdown_widget_validate_choice_factory)
from nominals.forms import NominalForm
from nominals.models import Nominal, NominalTransaction
from vat.forms import QuickVatForm
from vat.serializers import vat_object_for_input_dropdown_widget

from .forms import (CashBookHeaderForm, CashBookLineForm,
                    ReadOnlyCashBookHeaderForm, enter_lines, read_only_lines)
from .models import CashBookHeader, CashBookLine, CashBookTransaction


class CreateTransaction(CreateCashBookTransaction):
    header = {
        "model": CashBookHeader,
        "form": CashBookHeaderForm,
        "prefix": "header",
        "override_choices": ["cash_book"],
        "initial": {"total": 0},
    }
    line = {
        "model": CashBookLine,
        "formset": enter_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("cashbook:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("cashbook:create_on_the_fly"), prefix="vat")
    }
    template_name = "cashbook/create.html"
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    cash_book_transaction_model = CashBookTransaction
    module = "CB"

    # CONSIDER ADDING A DEFAULT TRANSACTION TYPE
    def get_header_form_type(self):
        t = self.request.GET.get("t", "cp")
        return t


class EditTransaction(EditCashBookTransaction):
    header = {
        "model": CashBookHeader,
        "form": CashBookHeaderForm,
        "prefix": "header",
        "override_choices": ["cash_book"],
        "initial": {"total": 0},
    }
    line = {
        "model": CashBookLine,
        "formset": enter_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    create_on_the_fly = {
        "nominal_form": NominalForm(action=reverse_lazy("cashbook:create_on_the_fly"), prefix="nominal"),
        "vat_form": QuickVatForm(action=reverse_lazy("cashbook:create_on_the_fly"), prefix="vat")
    }
    template_name = "cashbook/edit.html"
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    nominal_model = Nominal
    nominal_transaction_model = NominalTransaction
    cash_book_transaction_model = CashBookTransaction
    module = "CB"


class ViewTransaction(ViewTransactionOnLedgerOtherThanNominal):
    header = {
        "model": CashBookHeader,
        "form": ReadOnlyCashBookHeaderForm,
        "prefix": "header",
        "override_choices": ["cash_book"],
    }
    line = {
        "model": CashBookLine,
        "formset": read_only_lines,
        "prefix": "line",
        # VAT would not work at the moment
        "override_choices": ["nominal"]
        # because VAT requires (value, label, [ model field attrs ])
        # but VAT codes will never be that numerous
    }
    void_form_action = reverse_lazy("cashbook:void")
    void_form = BaseVoidTransactionForm
    template_name = "cashbook/view.html"
    nominal_transaction_model = NominalTransaction
    module = 'CB'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit_view_name"] = "cashbook:edit"
        return context


class VoidTransaction(BaseVoidTransaction):
    header_model = CashBookHeader
    nominal_transaction_model = NominalTransaction
    form_prefix = "void"
    form = BaseVoidTransactionForm
    success_url = reverse_lazy("cashbook:transaction_enquiry")
    module = 'CB'


load_options = input_dropdown_widget_load_options_factory(
    CashBookLineForm(), 25)


class TransactionEnquiry(NominalTransList):
    model = CashBookHeader
    fields = [
        ("module", "Module"),
        ("header", "Internal Ref"),
        ("ref", "Ref"),
        ("cash_book__name", "Cash Book"),
        ("period", "Period"),
        ("date", "Date"),
        ("total", "Total"),
    ]
    form_field_to_searchable_model_field = {
        "cash_book": "cash_book__name",
        "reference": "ref"
    }
    datetime_fields = ["created", ]
    datetime_format = '%d %b %Y'
    advanced_search_form_class = CashBookTransactionSearchForm
    template_name = "cashbook/transactions.html"
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
            CashBookTransaction.objects
            .select_related('cash_book__name')
            .all()
            .values(
                *[field[0] for field in self.fields[:-1]]
            )
            .annotate(total=Sum("value"))
            .order_by(*self.order_by())
        )


validate_choice = input_dropdown_widget_validate_choice_factory(
    CashBookLineForm())

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

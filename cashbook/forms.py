from django import forms

from accountancy.fields import (ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxForm, BaseCashBookLineForm,
                               BaseTransactionHeaderForm,
                               BaseTransactionLineForm,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineFormset)
from accountancy.helpers import input_dropdown_widget_attrs_config
from accountancy.layouts import (PlainFieldErrors, TableHelper,
                                 create_cashbook_header_helper)
from accountancy.widgets import InputDropDown
from nominals.models import Nominal

from .models import CashBookHeader, CashBookLine


class CashBookHeaderForm(BaseTransactionHeaderForm):
    class Meta:
        model = CashBookHeader
        fields = ('ref', 'date', 'total', 'type', 'period', 'cash_book')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = create_cashbook_header_helper()


class ReadOnlyCashBookHeaderForm(CashBookHeaderForm):
    date = forms.DateField()  # so datepicker is not used

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.fields["type"].widget = forms.TextInput(
            attrs={"class": "w-100 input"}
        )
        self.fields["cash_book"].widget = forms.TextInput(
            attrs={"class": "w-100 input"}
        )
        self.helper = create_cashbook_header_helper(read_only=True)
        self.initial["type"] = self.instance.get_type_display()


line_css_classes = {
    "Td": {
        "description": "can_highlight h-100 w-100 border-0",
        "nominal": "h-100 w-100 border-0",
        "goods": "can_highlight h-100 w-100 border-0",
        "vat_code": "h-100 w-100 border-0",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}

attrs_config = input_dropdown_widget_attrs_config(
    "nominals", ["nominal", "vat_code"])
nominal_attrs, vat_code_attrs = [attrs_config[attrs] for attrs in attrs_config]


class CashBookLineForm(BaseCashBookLineForm):
    class Meta:
        model = CashBookLine
        # WHY DO WE INCLUDE THE ID?
        fields = ('id', 'description', 'goods',
                  'nominal', 'vat_code', 'vat',)
        widgets = {
            "nominal": InputDropDown(attrs=nominal_attrs),
            "vat_code": InputDropDown(attrs=vat_code_attrs, model_attrs=['rate'])
        }
        # used in Transaction form set_querysets method
        ajax_fields = {
            "nominal": {
                "searchable_fields": ('name',),
                "querysets": {
                    "load": Nominal.objects.all().prefetch_related("children"),
                    "post": Nominal.objects.filter(children__isnull=True)
                },
                "iterator": RootAndLeavesModelChoiceIterator
            },
            "vat_code": {
                "searchable_fields": ('code', 'rate',),
                "iterator": ModelChoiceIteratorWithFields
            }
        }


class ReadOnlyCashBookLineForm(CashBookLineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.helpers = TableHelper(
            self._meta.fields,
            order=False,
            delete=False,
            css_classes={
                "Td": {
                    "description": "input-disabled text-left",
                    "nominal": "input-disabled text-left",
                    "goods": "input-disabled text-left",
                    "vat_code": "input-disabled text-left",
                    "vat": "input-disabled text-left"
                }
            },
            field_layout_overrides={
                'Td': {
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                    'amount': PlainFieldErrors
                }
            },
        ).render()


enter_lines = forms.modelformset_factory(
    CashBookLine,
    form=CashBookLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True

read_only_lines = forms.modelformset_factory(
    CashBookLine,
    form=ReadOnlyCashBookLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=0,
    can_order=True,
    can_delete=True  # both these keep the django crispy form template happy
    # there are of no actual use for the user
)

read_only_lines.include_empty_form = True

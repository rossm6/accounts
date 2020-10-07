from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndChildrenModelChoiceField,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxForm, BaseCashBookLineForm,
                               BaseTransactionHeaderForm,
                               BaseTransactionLineForm,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineFormset)
from accountancy.layouts import (PlainFieldErrors, TableHelper,
                                 create_cashbook_header_helper)
from accountancy.widgets import SelectWithDataAttr
from nominals.models import Nominal
from vat.models import Vat

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
        "goods": "can_highlight h-100 w-100 border-0",
        "nominal": "h-100 w-100 border-0",
        "vat_code": "h-100 w-100 border-0",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}


class CashBookLineForm(BaseCashBookLineForm):
    nominal = ModelChoiceFieldChooseIterator(
        queryset=Nominal.objects.none(),
        iterator=RootAndLeavesModelChoiceIterator,
        widget=forms.Select(
            attrs={"data-url": reverse_lazy("nominals:load_nominals")}
        )
    )
    vat_code = ModelChoiceFieldChooseIterator(
        iterator=ModelChoiceIteratorWithFields,
        queryset=Vat.objects.all(),
        widget=SelectWithDataAttr(
            attrs={
                "data-url": reverse_lazy("vat:load_vat_codes"),
                # i.e. add the rate value to the option as data-rate
                "data-attrs": ["rate"]
            }
        )
    )
    class Meta:
        model = CashBookLine
        # WHY DO WE INCLUDE THE ID?
        fields = ('id', 'description', 'goods',
                  'nominal', 'vat_code', 'vat',)
        ajax_fields = {
            "nominal": {
                "searchable_fields": ('name',),
                "querysets": {
                    "load": Nominal.objects.all().prefetch_related("children"),
                    "post": Nominal.objects.filter(children__isnull=True)
                },
            },
            "vat_code": {
                "searchable_fields": ('code', 'rate',),
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



class CashBookLineFormset(SaleAndPurchaseLineFormset):
    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'header')):
            return
        if self.header.total == 0:
            raise forms.ValidationError(
                _(
                    "Cash book transactions cannot be for a zero value."
                ),
                code="zero-cash-book-transaction"
            )


enter_lines = forms.modelformset_factory(
    CashBookLine,
    form=CashBookLineForm,
    formset=CashBookLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True

read_only_lines = forms.modelformset_factory(
    CashBookLine,
    form=ReadOnlyCashBookLineForm,
    formset=CashBookLineFormset,
    extra=0,
    can_order=True,
    can_delete=True  # both these keep the django crispy form template happy
    # there are of no actual use for the user
)

read_only_lines.include_empty_form = True

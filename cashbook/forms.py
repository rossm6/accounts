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
                               BaseTransactionSearchForm,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineFormset)
from accountancy.layouts import (PlainFieldErrors, TableHelper,
                                 create_cashbook_header_helper,
                                 create_transaction_enquiry_layout)
from accountancy.widgets import SelectWithDataAttr
from cashbook.models import CashBook
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
            attrs={"data-load-url": reverse_lazy("nominals:load_nominals")}
        )
    )
    vat_code = ModelChoiceFieldChooseIterator(
        iterator=ModelChoiceIteratorWithFields,
        queryset=Vat.objects.all(),
        widget=SelectWithDataAttr(
            attrs={
                "data-load-url": reverse_lazy("vat:load_vat_codes"),
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

class CashBookTransactionSearchForm(BaseTransactionSearchForm):
    cashbook = forms.ModelChoiceField(
        queryset=CashBook.objects.all(),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = create_transaction_enquiry_layout("cashbook")

from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxFormMixin,
                               BaseCashBookLineForm, BaseTransactionHeaderForm,
                               BaseTransactionLineForm,
                               NotNominalTransactionSearchForm,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineFormset)
from accountancy.layouts import (Div, LabelAndFieldAndErrors, PlainFieldErrors,
                                 TableHelper, create_cashbook_header_helper,
                                 create_transaction_enquiry_layout)
from accountancy.widgets import SelectWithDataAttr
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from nominals.models import Nominal
from vat.models import Vat

from cashbook.models import CashBook

from .models import CashBookHeader, CashBookLine


class CashBookForm(BaseAjaxFormMixin, forms.ModelForm):
    nominal = ModelChoiceFieldChooseIterator(
        queryset=Nominal.objects.none(),
        iterator=RootAndLeavesModelChoiceIterator,
        widget=forms.Select(
            attrs={"data-load-url": reverse_lazy("nominals:load_nominals")}
        )
    )

    class Meta:
        model = CashBook
        fields = ('name', 'nominal')
        ajax_fields = {
            "nominal": {
                "querysets": {
                    "load": Nominal.objects.all().prefetch_related("children"),
                    "post": Nominal.objects.filter(children__isnull=True)
                },
            }
        }

    def __init__(self, *args, **kwargs):
        if 'action' in kwargs:
            action = kwargs.pop("action")
        else:
            action = ''
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.form_action = action
        self.helper.attrs = {
            "data-form": "cashbook"
        }
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors('name', css_class="w-100 form-control"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'nominal',),
                    css_class="mt-2"
                ),
                css_class="modal-body"
            ),
            Div(
                HTML(
                    '<button type="button" class="btn btn-secondary cancel" data-dismiss="modal">Cancel</button>'),
                HTML('<button type="submit" class="btn btn-success">Save</button>'),
                css_class="modal-footer"
            )
        )


class CashBookHeaderForm(BaseTransactionHeaderForm):
    class Meta:
        model = CashBookHeader
        fields = ('ref', 'date', 'total', 'type',
                  'period', 'cash_book', 'vat_type')

    def __init__(self, *args, **kwargs):
        self.module_setting = "cash_book_period"
        super().__init__(*args, **kwargs)
        brought_forward = False
        analysis_required = CashBookHeader.get_types_requiring_analysis()
        t = self.initial.get("type")
        if t not in analysis_required:
            brought_forward = True
        self.helper = create_cashbook_header_helper(brought_forward=brought_forward)


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
            attrs={
                "data-load-url": reverse_lazy("nominals:load_nominals"),
                "data-selectize-type": 'nominal'
            }
        )
    )
    vat_code = ModelChoiceFieldChooseIterator(
        iterator=ModelChoiceIteratorWithFields,
        queryset=Vat.objects.all(),
        widget=SelectWithDataAttr(
            attrs={
                "data-load-url": reverse_lazy("vat:load_vat_codes"),
                # i.e. add the rate value to the option as data-rate
                "data-option-attrs": ["rate"],
                "data-selectize-type": 'vat'
            }
        ),
        required=False
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


class CashBookTransactionSearchForm(NotNominalTransactionSearchForm):
    cash_book = forms.ModelChoiceField(
        queryset=CashBook.objects.all(),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = create_transaction_enquiry_layout("cash_book")
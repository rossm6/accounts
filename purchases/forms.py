from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxForm, BaseLineFormset,
                               BaseTransactionHeaderForm,
                               BaseTransactionLineForm, BaseTransactionMixin,
                               BaseTransactionModelFormSet,
                               ReadOnlyBaseTransactionHeaderForm,
                               ReadOnlySaleAndPurchaseHeaderFormMixin,
                               ReadOnlySaleAndPurchaseLineFormMixin,
                               ReadOnlySaleAndPurchaseMatchingFormMixin,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineForm,
                               SaleAndPurchaseLineFormset,
                               SaleAndPurchaseMatchingForm,
                               SaleAndPurchaseMatchingFormset,
                               aged_matching_report_factory)
from accountancy.helpers import (delay_reverse_lazy,
                                 input_dropdown_widget_attrs_config)
from accountancy.layouts import (AdvSearchField, DataTableTdField, Div, Field,
                                 Hidden, PlainFieldErrors, TableHelper,
                                 create_transaction_header_helper)
from accountancy.widgets import InputDropDown
from contacts.forms import BaseContactForm
from items.models import Item
from nominals.models import Nominal
from vat.models import Vat

from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


"""

A note on formsets -

    For all the formsets, match, read_only_match, enter_lines, read_only_lines, i have added a "include_empty_form" attribute.
    I use this in my django crispy forms template to decide whether to include the empty form.

"""


class QuickSupplierForm(forms.ModelForm):
    """
    Used to create a supplier on the fly in the transaction views
    """
    class Meta:
        model = Supplier
        fields = ('code', )


class SupplierForm(BaseContactForm):
    class Meta(BaseContactForm.Meta):
        model = Supplier


class PurchaseHeaderForm(SaleAndPurchaseHeaderFormMixin, BaseTransactionHeaderForm):

    class Meta:
        model = PurchaseHeader
        fields = ('cash_book', 'supplier', 'ref', 'date',
                  'due_date', 'total', 'type', 'period')
        widgets = {
            "supplier": forms.Select(
                attrs={
                    "data-form": "supplier",
                    "data-form-field": "supplier-code",
                    "data-creation-url": reverse_lazy("purchases:create_on_the_fly"),
                    "data-load-url": reverse_lazy("purchases:load_suppliers"),
                    "data-contact-field": True
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.data and not self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.none()
        if self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.filter(
                pk=self.instance.supplier_id)


class ReadOnlyPurchaseHeaderForm(ReadOnlySaleAndPurchaseHeaderFormMixin, ReadOnlyBaseTransactionHeaderForm, PurchaseHeaderForm):
    pass


attrs_config = input_dropdown_widget_attrs_config(
    "purchases", ["item", "nominal", "vat_code"])
item_attrs, nominal_attrs, vat_code_attrs = [
    attrs_config[attrs] for attrs in attrs_config]


class PurchaseLineForm(SaleAndPurchaseLineForm):
    class Meta:
        model = PurchaseLine
        # WHY DO WE INCLUDE THE ID?
        fields = ('id', 'item', 'description', 'goods',
                  'nominal', 'vat_code', 'vat',)
        widgets = {
            "item": InputDropDown(attrs=item_attrs),
            "nominal": InputDropDown(attrs=nominal_attrs),
            "vat_code": InputDropDown(attrs=vat_code_attrs, model_attrs=['rate'])
        }
        # used in Transaction form set_querysets method
        ajax_fields = {
            "item": {
                "empty_label": "(None)",
                "searchable_fields": ('code', 'description')
            },
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


class ReadOnlyPurchaseLineForm(ReadOnlySaleAndPurchaseLineFormMixin, PurchaseLineForm):
    pass


enter_lines = forms.modelformset_factory(
    PurchaseLine,
    form=PurchaseLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True

read_only_lines = forms.modelformset_factory(
    PurchaseLine,
    form=ReadOnlyPurchaseLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=0,
    can_order=True,
    can_delete=True  # both these keep the django crispy form template happy
    # there are of no actual use for the user
)

read_only_lines.include_empty_form = True

# SHOULD NOT INHERIT FROM BASETRANSACTIONMIXIN BECAUSE WE WANT TO SEE CREDITS WITH A MINUS SIGN


class PurchaseMatchingForm(SaleAndPurchaseMatchingForm):
    type = forms.ChoiceField(choices=PurchaseHeader.type_choices, widget=forms.Select(
        attrs={"disabled": True, "readonly": True}))
    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted

    class Meta(SaleAndPurchaseMatchingForm.Meta):
        model = PurchaseMatching


class ReadOnlyPurchaseMatchingForm(ReadOnlySaleAndPurchaseMatchingFormMixin, PurchaseMatchingForm):
    pass


match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

match.include_empty_form = False

read_only_match = forms.modelformset_factory(
    PurchaseMatching,
    form=ReadOnlyPurchaseMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

read_only_match.include_empty_form = False

# returns form class
CreditorForm = aged_matching_report_factory(
    Supplier,
    reverse_lazy("purchases:create_on_the_fly"),
    reverse_lazy("purchases:load_suppliers")
)

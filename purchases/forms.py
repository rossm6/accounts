from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (ModelChoiceFieldChooseIterator,
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
from accountancy.layouts import (AdvSearchField, DataTableTdField, Div, Field,
                                 Hidden, LabelAndFieldAndErrors,
                                 PlainFieldErrors, TableHelper,
                                 create_transaction_header_helper)
from accountancy.widgets import SelectWithDataAttr
from contacts.forms import BaseContactForm, ModalContactForm
from nominals.models import Nominal
from vat.models import Vat

from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


"""

A note on formsets -

    For all the formsets, match, read_only_match, enter_lines, read_only_lines, i have added a "include_empty_form" attribute.
    I use this in my django crispy forms template to decide whether to include the empty form.

"""


class SupplierForm(BaseContactForm):
    """
    `action` is what reverse_lazy returns.  If you aren't careful,
    and deviate from below, you will get a circulate import error.

    I don't understand what is going on fully.
    """
    class Meta(BaseContactForm.Meta):
        model = Supplier

    def __init__(self, *args, **kwargs):
        if (action := kwargs.get("action")) is not None:
            kwargs.pop("action")
        else:
            action = ""
        super().__init__(*args, **kwargs)
        self.helper.form_action = action

class ModalSupplierForm(ModalContactForm, SupplierForm):
    pass


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
                    "data-creation-url": reverse_lazy("contacts:create_supplier"),
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


class PurchaseLineForm(SaleAndPurchaseLineForm):
    """
    WARNING, WHEN YOU COME TO REFACTOR THE CODE - 

    You cannot instantiate a ModelForm and then just override the iterator.
    It has to be done during the instantiation of the field it seems.

    Also, the widget seems it cannot be defined in the Meta class

    """
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
        model = PurchaseLine
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
    reverse_lazy("contacts:create_supplier"),
    reverse_lazy("purchases:load_suppliers")
)

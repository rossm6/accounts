from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxForm, BaseAjaxFormMixin,
                               BaseLineFormset, BaseTransactionHeaderForm,
                               BaseTransactionLineForm, BaseTransactionMixin,
                               BaseTransactionModelFormSet,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineForm,
                               SaleAndPurchaseLineFormset,
                               SaleAndPurchaseMatchingForm,
                               SaleAndPurchaseMatchingFormset,
                               SalesAndPurchaseTransactionSearchForm,
                               aged_matching_report_factory)
from accountancy.layouts import (AdvSearchField, DataTableTdField, Div, Field,
                                 Hidden, LabelAndFieldAndErrors,
                                 PlainFieldErrors, TableHelper,
                                 create_transaction_enquiry_layout,
                                 create_transaction_header_helper)
from accountancy.widgets import SelectWithDataAttr
from nominals.models import Nominal
from vat.models import Vat

from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


"""

A note on formsets -

    For all the formsets, match, read_only_match, enter_lines, read_only_lines, i have added a "include_empty_form" attribute.
    I use this in my django crispy forms template to decide whether to include the empty form.

"""

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
                    "data-creation-url": reverse_lazy("contacts:create"),
                    "data-load-url": reverse_lazy("purchases:load_suppliers"),
                    "data-contact-field": True
                    # i think the last two are the only needed
                    # attributes.  NEED TO CHECK.
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
        # at the moment the user can choose any contact
        # will filter the queryset to only suppliers when refactoring this
        # so that it inherits from the BaseAjaxMixinForm


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
            attrs={
                "data-load-url": reverse_lazy("nominals:load_nominals"),
                "data-selectize-type": 'nominal'
            }
        ),
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


enter_lines = forms.modelformset_factory(
    PurchaseLine,
    form=PurchaseLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True


class PurchaseMatchingForm(SaleAndPurchaseMatchingForm):
    type = forms.ChoiceField(choices=PurchaseHeader.types, widget=forms.Select(
        attrs={"disabled": True, "readonly": True}))
    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted

    class Meta(SaleAndPurchaseMatchingForm.Meta):
        model = PurchaseMatching


match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

match.include_empty_form = False

# returns form class
CreditorForm = aged_matching_report_factory(
    Supplier,
    reverse_lazy("contacts:create"),
    reverse_lazy("purchases:load_suppliers")
)


class PurchaseTransactionSearchForm(BaseAjaxFormMixin, SalesAndPurchaseTransactionSearchForm):
    """
    This is not a model form.  The Meta attribute is only for the Ajax
    form implementation.
    """
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        widget=forms.Select(
            attrs={
                "data-load-url": reverse_lazy("purchases:load_suppliers"),
                "data-selectize-type": 'contact'
            }
        ),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = create_transaction_enquiry_layout(
            "supplier", search_within=True)

    class Meta:
        # not a model form
        ajax_fields = {
            "supplier": {}  # need to change the base ajax form so it can just accept a list of fields
        }

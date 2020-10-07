from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.urls import reverse_lazy

from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseTransactionHeaderForm,
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
from accountancy.helpers import input_dropdown_widget_attrs_config
from accountancy.layouts import Div, LabelAndFieldAndErrors
from accountancy.widgets import SelectWithDataAttr
from contacts.forms import BaseContactForm, ModalContactForm
from nominals.models import Nominal
from vat.models import Vat

from .models import Customer, SaleHeader, SaleLine, SaleMatching


class CustomerForm(BaseContactForm):
    class Meta(BaseContactForm.Meta):
        model = Customer

    def __init__(self, *args, **kwargs):
        if (action := kwargs.get("action")) is not None:
            kwargs.pop("action")
        else:
            action = ""
        super().__init__(*args, **kwargs)
        self.helper.form_action = action
        # same as the PL form so needs factoring out


class ModalCustomerForm(ModalContactForm, CustomerForm):
    pass


class SaleHeaderForm(SaleAndPurchaseHeaderFormMixin, BaseTransactionHeaderForm):

    class Meta:
        model = SaleHeader
        fields = ('cash_book', 'customer', 'ref', 'date',
                  'due_date', 'total', 'type', 'period')
        widgets = {
            "customer": forms.Select(
                attrs={
                    "data-form": "customer",
                    "data-form-field": "customer-code",
                    "data-creation-url": reverse_lazy("contacts:create_customer"),
                    "data-load-url": reverse_lazy("sales:load_customers"),
                    "data-contact-field": True
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # FIX ME - Same as PL ledger.  Need to improve this.
        # With general solution.

        if not self.data and not self.instance.pk:
            self.fields["customer"].queryset = Customer.objects.none()
        if self.instance.pk:
            self.fields["customer"].queryset = Customer.objects.filter(
                pk=self.instance.customer_id)


class ReadOnlySaleHeaderForm(ReadOnlySaleAndPurchaseHeaderFormMixin, ReadOnlyBaseTransactionHeaderForm, SaleHeaderForm):
    pass


attrs_config = input_dropdown_widget_attrs_config(
    "sales", ["nominal", "vat_code"])
nominal_attrs, vat_code_attrs = [
    attrs_config[attrs] for attrs in attrs_config]


class SaleLineForm(SaleAndPurchaseLineForm):
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
        model = SaleLine
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


class ReadOnlySaleLineForm(ReadOnlySaleAndPurchaseLineFormMixin, SaleLineForm):
    pass


enter_lines = forms.modelformset_factory(
    SaleLine,
    form=SaleLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True

read_only_lines = forms.modelformset_factory(
    SaleLine,
    form=ReadOnlySaleLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=0,
    can_order=True,
    can_delete=True  # both these keep the django crispy form template happy
    # there are of no actual use for the user
)

read_only_lines.include_empty_form = True

# SHOULD NOT INHERIT FROM BASETRANSACTIONMIXIN BECAUSE WE WANT TO SEE CREDITS WITH A MINUS SIGN


class SaleMatchingForm(SaleAndPurchaseMatchingForm):
    type = forms.ChoiceField(choices=SaleHeader.type_choices, widget=forms.Select(
        attrs={"disabled": True, "readonly": True}))
    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted

    class Meta(SaleAndPurchaseMatchingForm.Meta):
        model = SaleMatching


class ReadOnlySaleMatchingForm(ReadOnlySaleAndPurchaseMatchingFormMixin, SaleMatchingForm):
    pass


match = forms.modelformset_factory(
    SaleMatching,
    form=SaleMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

match.include_empty_form = False

read_only_match = forms.modelformset_factory(
    SaleMatching,
    form=ReadOnlySaleMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

read_only_match.include_empty_form = False

# returns form class
DebtorForm = aged_matching_report_factory(
    Customer,
    reverse_lazy("sales:create_on_the_fly"),
    reverse_lazy("sales:load_customers")
)

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from accountancy.layouts import Div, LabelAndFieldAndErrors

from django import forms
from django.urls import reverse_lazy

from accountancy.fields import (ModelChoiceIteratorWithFields,
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
from accountancy.widgets import InputDropDown
from nominals.models import Nominal

from .models import Customer, SaleHeader, SaleLine, SaleMatching


class QuickCustomerForm(forms.ModelForm):

    class Meta:
        model = Customer
        fields = ('code', )


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ('code', 'name', 'email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                LabelAndFieldAndErrors(
                    'code',
                    css_class="form-control form-control-sm w-100"
                ),
                css_class="form-group"
            ),
            Div(
                LabelAndFieldAndErrors(
                    'name',
                    css_class="form-control form-control-sm w-100"
                ),
                css_class="form-group"
            ),
            Div(
                LabelAndFieldAndErrors(
                    'email',
                    css_class="form-control form-control-sm w-100"
                ),
                css_class="form-group"
            ),
        )


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
                    "data-creation-url": reverse_lazy("sales:create_on_the_fly"),
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
    "sales", ["item", "nominal", "vat_code"])
item_attrs, nominal_attrs, vat_code_attrs = [
    attrs_config[attrs] for attrs in attrs_config]


class SaleLineForm(SaleAndPurchaseLineForm):
    class Meta:
        model = SaleLine
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

from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxFormMixin, BaseTransactionHeaderForm,
                               SaleAndPurchaseHeaderFormMixin,
                               SaleAndPurchaseLineForm,
                               SaleAndPurchaseLineFormset,
                               SaleAndPurchaseMatchingForm,
                               SaleAndPurchaseMatchingFormset,
                               SalesAndPurchaseTransactionSearchForm)
from accountancy.layouts import (Div, LabelAndFieldAndErrors,
                                 create_transaction_enquiry_layout)
from accountancy.widgets import SelectWithDataAttr
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.urls import reverse_lazy
from nominals.models import Nominal
from purchases.forms import CreditorsForm
from vat.models import Vat

from sales.models import Customer, SaleHeader, SaleLine, SaleMatching


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
                    "data-creation-url": reverse_lazy("contacts:create"),
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


class SaleLineForm(SaleAndPurchaseLineForm):
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


enter_lines = forms.modelformset_factory(
    SaleLine,
    form=SaleLineForm,
    formset=SaleAndPurchaseLineFormset,
    extra=5,
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True


class SaleMatchingForm(SaleAndPurchaseMatchingForm):
    type = forms.ChoiceField(choices=SaleHeader.types, widget=forms.Select(
        attrs={"disabled": True, "readonly": True}))
    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted
    # search 'CLIENT JS ITEM 1'.  Currently in edit_matching_js.html

    class Meta(SaleAndPurchaseMatchingForm.Meta):
        model = SaleMatching


match = forms.modelformset_factory(
    SaleMatching,
    form=SaleMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

match.include_empty_form = False


class DebtorsForm(CreditorsForm):
    from_contact_field = "from_customer"
    to_contact_field = "to_customer"
    contact_field_name = "customer"
    contact_load_url = reverse_lazy("sales:load_customers")
    from_customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "data-form": contact_field_name,
                "data-form-field": contact_field_name + "-code",
                "data-creation-url": CreditorsForm.contact_creation_url,
                "data-load-url": contact_load_url,
                "data-contact-field": True
            }
        )
    )
    to_customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "data-form": contact_field_name,
                "data-form-field": contact_field_name + "-code",
                "data-creation-url": CreditorsForm.contact_creation_url,
                "data-load-url": contact_load_url,
                "data-contact-field": True
            }
        )
    )

    class Meta:
        ajax_fields = {
            "to_customer": {},
            "from_customer": {}
        }

class SaleTransactionSearchForm(BaseAjaxFormMixin, SalesAndPurchaseTransactionSearchForm):
    """
    This is not a model form.  The Meta attribute is only for the Ajax
    form implementation.
    """
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        widget=forms.Select(
            attrs={
                "data-load-url": reverse_lazy("sales:load_customers"),
                "data-selectize-type": 'contact'
            }
        ),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = create_transaction_enquiry_layout(
            "customer", search_within=True)

    class Meta:
        # not a model form
        ajax_fields = {
            "customer": {}  # need to change the base ajax form so it can just accept a list of fields
        }

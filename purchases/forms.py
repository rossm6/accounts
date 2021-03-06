from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxFormMixin, BaseLineFormset,
                               BaseTransactionHeaderForm,
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
from controls.models import Period
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from nominals.models import Nominal
from tempus_dominus.widgets import DatePicker
from vat.models import Vat

from purchases.models import (PurchaseHeader, PurchaseLine, PurchaseMatching,
                              Supplier)

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
        self.module_setting = "purchases_period"
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
        required=False
    )

    class Meta:
        model = PurchaseLine
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
    # search 'CLIENT JS ITEM 1'.  Currently in edit_matching_js.html

    class Meta(SaleAndPurchaseMatchingForm.Meta):
        model = PurchaseMatching


match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=SaleAndPurchaseMatchingFormset
)

match.include_empty_form = False


class CreditorsForm(BaseAjaxFormMixin, forms.Form):
    from_contact_field = "from_supplier"
    to_contact_field = "to_supplier"
    contact_field_name = "supplier"
    contact_creation_url = reverse_lazy("contacts:create")
    contact_load_url = reverse_lazy("purchases:load_suppliers")
    from_supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "data-form": contact_field_name,
                "data-form-field": contact_field_name + "-code",
                "data-creation-url": contact_creation_url,
                "data-load-url": contact_load_url,
                "data-contact-field": True
            }
        )
    )
    to_supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "data-form": contact_field_name,
                "data-form-field": contact_field_name + "-code",
                "data-creation-url": contact_creation_url,
                "data-load-url": contact_load_url,
                "data-contact-field": True
            }
        )
    )
    period = forms.ModelChoiceField(
        queryset=Period.objects.all()
    )
    show_transactions = forms.BooleanField(required=False)
    use_adv_search = forms.BooleanField(required=True, initial=True)

    def clean(self):
        cleaned_data = super().clean()
        if (
            (to_contact := cleaned_data.get(self.to_contact_field)) and
            (from_contact := cleaned_data.get(self.from_contact_field))
            and to_contact.pk < from_contact.pk
        ):
            raise forms.ValidationError(
                _(
                    f"This is not a valid range for {self.contact_field_name}s "
                    f"because the second {self.contact_field_name} you choose comes before the first {self.contact_field_name}"
                ),
                code=f"invalid {self.contact_field_name} range"
            )
        return cleaned_data

    class Meta:
        ajax_fields = {
            "to_supplier": {},
            "from_supplier": {}
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        self.from_contact_field, css_class="w-100 form-control form-control-sm"),
                    css_class="col"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        self.to_contact_field, css_class="w-100 form-control form-control-sm"),
                    css_class="col"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        "period", css_class="w-100 form-control form-control-sm"),
                    css_class="col"
                ),
                css_class="row"
            ),
            Div(
                Div(
                    LabelAndFieldAndErrors("show_transactions"),
                    css_class="col"
                ),
                Hidden('adv_search_form', True),
                css_class="mt-4 row"
            ),
            Div(
                HTML("<button class='btn btn-primary'>Report</button>"),
                css_class="text-right mt-3"
            )
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
            "supplier", search_within=True, include_voided=True)

    class Meta:
        # not a model form
        ajax_fields = {
            "supplier": {}  # need to change the base ajax form so it can just accept a list of fields
        }

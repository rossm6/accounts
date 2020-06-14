from django import forms
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField)
from accountancy.forms import (AjaxForm, LabelAndFieldOnly, TableHelper,
                               create_tbody_helper, create_thead_helper,
                               create_transaction_header_helper, PlainFieldErrors)
from accountancy.helpers import delay_reverse_lazy
from accountancy.widgets import InputDropDown
from items.models import Item
from nominals.models import Nominal

from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


class BaseTransactionModelFormSet(forms.BaseModelFormSet):

    def get_ordering_widget(self):
        return forms.HiddenInput(attrs={'class': 'ordering'})


class PurchaseHeaderForm(forms.ModelForm):

    date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        )
    )
    due_date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        )
    )

    class Meta:
        model = PurchaseHeader
        fields = ('supplier', 'ref', 'date', 'due_date', 'total', 'type',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = create_transaction_header_helper(
            {
                'contact': 'supplier',
            }
        )
        # FIX ME - The supplier field should use the generic AjaxModelChoice Field class I created
        # this then takes care out of this already
        # Form would then need to inherit from AjaxForm
        if not self.data:
            self.fields["supplier"].queryset = Supplier.objects.none()

    def clean(self):
        super().clean()
        # raise forms.ValidationError("test")
        

    def save(self, commit=True):
        instance = super().save(commit=False)
        # the user should never have the option to directly
        # change the due amount or the paid amount
        # paid will default to zero
        instance.due = instance.total - instance.paid
        if commit:
            instance.save()
        return instance


class PurchaseLineFormset(BaseTransactionModelFormSet):
    # Might be helpful one day - https://reinbach.com/blog/django-formsets-with-extra-params/

    def __init__(self, *args, **kwargs):
        if 'header' in kwargs:
            self.header = kwargs.pop("header")
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        # raise forms.ValidationError("line formset error") testing purposes
        # header has not been saved by this point
        # forms each have an instance by now
        # so change values on the instance not in cleaned data
        # if any of the forms have failed you might not want to do further validation
        # so could do this -
        # if any(self.errors):
        #   return
        # example - https://docs.djangoproject.com/en/3.0/topics/forms/formsets/#custom-formset-validation
        # note that the model formset clean method by default checks the integrity of the data
        # see - https://docs.djangoproject.com/en/3.0/topics/forms/formsets/#custom-formset-validation


class PurchaseLineForm(AjaxForm):

    item = AjaxModelChoiceField(
        get_queryset=Item.objects.none(),
        load_queryset=Item.objects.all(),
        post_queryset=Item.objects.all(),
        inst_queryset= lambda inst : Item.objects.filter(pk=inst.item_id),
        widget=InputDropDown(
            attrs={
                "data-newitem": "#new_item",
                "data-load-url": delay_reverse_lazy("purchases:load_options", "field=item"),
                "data-validation-url": delay_reverse_lazy("purchases:validate_choice", "field=item")
            }
        ),
        empty_label="(None)",
        searchable_fields=('code', 'description')
    )
    nominal = AjaxRootAndLeavesModelChoiceField(
        widget=InputDropDown(
            attrs={
                "data-newitem": "#new_nominal",
                "data-load-url": delay_reverse_lazy("purchases:load_options", "field=nominal"),
                "data-validation-url": delay_reverse_lazy("purchases:validate_choice", "field=nominal")
            }
        ),
        empty_label=None,
        get_queryset=Nominal.objects.none(),
        load_queryset=Nominal.objects.all().prefetch_related("children"),
        post_queryset=Nominal.objects.filter(children__isnull=True),
        inst_queryset= lambda inst : Nominal.objects.filter(pk=inst.nominal_id),
        searchable_fields=('name',)
    )

    class Meta:
        model = PurchaseLine
        fields = ('item', 'description', 'nominal', 'amount',)
        ajax_fields = ('item', 'nominal',) # used in Transaction form set_querysets method

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css_classes = {
            "Td": {
                "item": "h-100 w-100 border-0",
                "description": "can_highlight h-100 w-100 border-0",
                "nominal": "h-100 w-100 border-0",
                "amount": "can_highlight h-100 w-100 border-0"
            }
        }
        self.helpers = TableHelper(
            PurchaseLineForm.Meta.fields,
            order=True,
            delete=True,
            css_classes=css_classes,
            field_layout_overrides={
                'Td': {
                    'item': PlainFieldErrors,
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                    'amount': PlainFieldErrors
                }
            }
        ).render()


    # testing purposes to check if non_field_errors come through in UI
    # def clean(self):
    #     cleaned_data = super().clean()
    #     raise forms.ValidationError("non field error on line form")
    #     return cleaned_data


enter_lines = forms.modelformset_factory(
    PurchaseLine,
    form=PurchaseLineForm, 
    formset=PurchaseLineFormset, 
    extra=5, 
    can_order=True
)



"""

With the PurchaseMatching form and formset, we might as well always
just pass the header to the form rather than ever render it as a field.

We could use an inline formset for the edit view because the header
will have been created by this point.

"""


class PurchaseMatchingForm(forms.ModelForm):

    """
    When creating new transactions there is the option to match
    the new transaction to existing transactions.  This form will
    therefore have to be built on the client dynamically for creating
    new transactions.


    CAUTION -

    The type field needs the label overriding to the display
    name of the value.  This is easy when we have an instance;
    if the submitted form though is for a new instance we
    have to get the label based on the cleaned user input.  This
    is done in clean

    """

    type = forms.ChoiceField(choices=PurchaseHeader.type_choices, widget=forms.Select(attrs={"disabled": True, "readonly": True})) 
    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted
    ref = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"readonly": True}))
    total = forms.DecimalField(decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={"readonly": True}))
    paid = forms.DecimalField(decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={"readonly": True}))
    due = forms.DecimalField(decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={"readonly": True}))

    class Meta:
        model = PurchaseMatching
        fields = ('matched_to', 'value',)
        widgets = {
            'matched_to': forms.TextInput
        }

    def __init__(self, *args, **kwargs):
        # this logic is in case we ever need the form without the formset
        # but with a formset the keyword argument will not be passed
        if match_by := kwargs.get("match_by"):
            self.match_by = match_to
            kwargs.pop("match_by")
        super().__init__(*args, **kwargs)
        print(self.fields["type"].widget.__dict__)
        # print(self.fields["matched_to"].widget.__dict__)
        # Question - will the matched_to.pk show in the input field when editing ?
        if not self.data and not self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.none()
        elif self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.get(pk=self.instance.matched_to)
        self.helpers = TableHelper(
            ('type', 'ref', 'total', 'paid', 'due',) + 
            PurchaseMatchingForm.Meta.fields,
            css_classes={
                "Td": {
                    "type": "input-disabled",
                    "ref": "input-disabled",
                    "total": "input-disabled",
                    "paid": "input-disabled",
                    "due": "input-disabled",
                    "value": "w-100 h-100 border-0 pl-2"
                }
            },
            field_layout_overrides={
                'Td': {
                    'value': PlainFieldErrors,
                }
            }
        ).render()


    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.matched_by = self.match_by
        if commit:
            instance.save()
        return instance



class PurchaseMatchingFormset(BaseTransactionModelFormSet):

    """
    Match by is the header record which is being used to match
    the other headers against -

    E.g.

    The user creates a new receipt for value -100.00
    And they select to match an invoice against this in the same posting.

    In this situation the receipt is the "match_by" header and the
    "match_to" header is the invoice.

    """

    def __init__(self, *args, **kwargs):
        if 'match_by' in kwargs:
            self.match_by = kwargs.pop("match_by")
        super().__init__(*args, **kwargs)


    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        try:
            form.match_by = self.match_by
        except AttributeError as e:
            pass
        return form


    def clean(self):
        super().clean()


match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=PurchaseMatchingFormset
)

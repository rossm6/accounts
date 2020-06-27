from django import forms
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField,
                                ModelChoiceIteratorWithFields)
from accountancy.forms import (AjaxForm, DataTableTdField, LabelAndFieldOnly,
                               PlainFieldErrors, TableHelper,
                               create_payment_transaction_header_helper,
                               create_transaction_header_helper, BaseTransactionMixin)
from accountancy.helpers import delay_reverse_lazy
from accountancy.widgets import InputDropDown
from items.models import Item
from nominals.models import Nominal
from vat.models import Vat

from .models import PurchaseHeader, PurchaseLine, PurchaseMatching, Supplier


class BaseTransactionModelFormSet(forms.BaseModelFormSet):

    def get_ordering_widget(self):
        return forms.HiddenInput(attrs={'class': 'ordering'})


# FIX ME - this should inherit from a base class PaymentHeader in accountancy.forms
class PaymentHeader(BaseTransactionMixin, forms.ModelForm):

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

    class Meta:
        model = PurchaseHeader
        fields = ('supplier', 'ref', 'date', 'total', 'type',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            self.fields['type'].choices = PurchaseHeader.type_payments
        self.helper = create_payment_transaction_header_helper(
            {
                'contact': 'supplier',
            }
        )
        # FIX ME - The supplier field should use the generic AjaxModelChoice Field class I created
        # this then takes care out of this already
        # Form would then need to inherit from AjaxForm
        if not self.data and not self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.none()
        if self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.filter(pk=self.instance.supplier_id)


    def clean(self):
        cleaned_data = super().clean()
        type = cleaned_data.get("type")
        total = cleaned_data.get("total")
        if total:
            if type in ("p", "bp"):
                cleaned_data["total"] = -1 * total
        return cleaned_data


    def save(self, commit=True):
        instance = super().save(commit=False)
        # the user should never have the option to directly
        # change the due amount or the paid amount
        # paid will default to zero
        instance.due = instance.total - instance.paid
        if commit:
            instance.save()
        return instance



class PurchaseHeaderForm(BaseTransactionMixin, forms.ModelForm):

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
        ),
        required=False
    )

    class Meta:
        model = PurchaseHeader
        fields = ('supplier', 'ref', 'date', 'due_date', 'total', 'type',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.initial['type'] in ("bp", 'p', 'br', 'r'): # FIX ME - we need a global way of checking this
            # as we are repeating ourselves
            payment_form = True
            print("true")
        else:
            payment_form = False
        self.helper = create_transaction_header_helper(
            {
                'contact': 'supplier',
            },
            payment_form
        )
        # FIX ME - The supplier field should use the generic AjaxModelChoice Field class I created
        # this then takes care out of this already
        # Form would then need to inherit from AjaxForm
        if not self.data and not self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.none()
        if self.instance.pk:
            self.fields["supplier"].queryset = Supplier.objects.filter(pk=self.instance.supplier_id)

    def clean(self):
        cleaned_data = super().clean()
        type = cleaned_data.get("type")
        total = cleaned_data.get("total")
        if total:
            if type in ("c", "bc", "p", "bp"):
                cleaned_data["total"] = -1 * total
        return cleaned_data

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
            if header := kwargs.get('header'): # header could be None
                self.header = header
            kwargs.pop("header")
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'header')):
            return
        goods = 0
        vat = 0
        total = 0
        for form in self.forms:
            if form.empty_permitted and form.has_changed(): # because there are no forms errors every form which has changed
                # must contain valid goods, vat, and total figures
                # otherwise could try checking is_valid
                goods += form.instance.goods
                vat += form.instance.vat
                total += ( form.instance.goods + form.instance.vat )
        if self.header.total != 0 and self.header.total != total:
            raise forms.ValidationError(
                _(
                    "The total of the lines does not equal the total you entered."
                ),
                code="invalid-total"
            )
        self.header.goods = goods
        self.header.vat = vat
        self.header.total = total
        self.header.due = total
        # this header will be passed to the matching formset
        # we need to update this value for this formset
        

class PurchaseLineForm(BaseTransactionMixin, AjaxForm):

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

    vat_code = AjaxModelChoiceField(
        widget=InputDropDown(
            attrs={
                "data-new-vat-code": "#new-vat-code",
                "data-load-url": delay_reverse_lazy("purchases:load_options", "field=vat_code"),
                "data-validation-url": delay_reverse_lazy("purchases:validate_choice", "field=vat_code")
            },
            model_attrs=['rate']
        ),
        empty_label=None,
        get_queryset=Vat.objects.none(),
        load_queryset=Vat.objects.all(),
        post_queryset=Vat.objects.all(),
        inst_queryset= lambda inst : Vat.objects.filter(pk=inst.vat_code_id),
        searchable_fields=('code', 'rate',),
        iterator=ModelChoiceIteratorWithFields
    )

    class Meta:
        model = PurchaseLine
        fields = ('item', 'description', 'goods', 'nominal', 'vat_code', 'vat',)
        ajax_fields = ('item', 'nominal', 'vat_code', ) # used in Transaction form set_querysets method
        widgets = {
            "vat_code": InputDropDown(
                attrs={
                    "data-new-vat-code": "#new-vat-code",
                    "data-load-url": delay_reverse_lazy("purchases:load_options", "field=vat_code"),
                    "data-validation-url": delay_reverse_lazy("purchases:validate_choice", "field=vat_code")
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css_classes = {
            "Td": {
                "item": "h-100 w-100 border-0",
                "description": "can_highlight h-100 w-100 border-0",
                "nominal": "h-100 w-100 border-0",
                "goods": "can_highlight h-100 w-100 border-0",
                "vat_code": "h-100 w-100 border-0",
                "vat": "can_highlight w-100 h-100 border-0"
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


# SHOULD NOT INHERIT FROM BASETRANSACTIONMIXIN BECAUSE WE WANT TO SEE CREDITS WITH A MINUS SIGN
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
        fields = ('matched_to', 'value', 'id')
        widgets = {
            'matched_to': forms.TextInput
        }

    def __init__(self, *args, **kwargs):
        # this logic is in case we ever need the form without the formset
        # but with a formset the keyword argument will not be passed
        if 'match_by' in kwargs:
            if match_by := kwargs.get('match_by'): # match_by could be None
                self.match_by = match_by
            kwargs.pop("match_by")

        # print(self.fields["matched_to"].widget.__dict__)
        # Question - will the matched_to.pk show in the input field when editing ?

        super().__init__(*args, **kwargs)

        if not self.data and not self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.none()
        # if self.instance.pk:
        #     if self.match_by.pk == self.instance.matched_to_id:
        #         matched_header = self.instance.matched_by
        #     else:
        #         matched_header = self.instance.matched_to
        #     self.fields["type"].initial = matched_header.type
        #     self.fields["ref"].initial = matched_header.ref
        #     self.fields["total"].initial = matched_header.total
        #     self.fields["paid"].initial = matched_header.paid
        #     self.fields["due"].initial = matched_header.due
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
                    'type': DataTableTdField,
                    'ref': DataTableTdField,
                    'total': DataTableTdField,
                    'paid': DataTableTdField,
                    'due': DataTableTdField,
                    'value': PlainFieldErrors,
                }
            }
        ).render()


    def clean(self):
        cleaned_data = super().clean()
        initial_value = self.initial.get("value", 0)
        matched_to = cleaned_data.get("matched_to")
        value = cleaned_data.get("value")
        if matched_to and value:
            if matched_to.due > 0:
                if value < 0:
                    raise forms.ValidationError(
                        _(
                            "Cannot match less than value outstanding"
                        ),
                        code="invalid-match"
                    )
                elif value > matched_to.due + initial_value:
                    raise forms.ValidationError(
                        _(
                            'Cannot match more than value outstanding'
                        )
                    )
            elif matched_to.due < 0:
                if value > 0:
                    raise forms.ValidationError(
                        _(
                            "Cannot match less than value outstanding"
                        ),
                        code="invalid-match"
                    )
                elif value < matched_to.due - initial_value:
                    raise forms.ValidationError(
                        _(
                            'Cannot match more than value outstanding'
                        )
                    )


    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.matched_by = self.match_by
        if commit:
            instance.save()
        return instance



class PurchaseMatchingFormset(BaseTransactionModelFormSet):

    """

    Match by has two meaning depending on the context.

    For create, match by is the header record which is being used to match
    the other headers against -

        E.g.

        The user creates a new receipt for value -100.00
        And they select to match an invoice against this in the same posting.

        In this situation the receipt is the "match_by" header and the
        "match_to" header is the invoice.

    For edit, match by is the header record we are viewing to edit.
    In terms of the matching record itself, this header could correspond
    to either the matching_by or the matching_to.

    """

    def __init__(self, *args, **kwargs):
        if 'match_by' in kwargs:
            if match_by := kwargs.get('match_by'): # match_by could be None
                self.match_by = match_by
            kwargs.pop("match_by")
        super().__init__(*args, **kwargs)


    def _construct_form(self, i, **kwargs):
        if hasattr(self, 'match_by'):
            kwargs["match_by"] = self.match_by
        form = super()._construct_form(i, **kwargs)
        return form


    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'match_by')):
            return
        self.headers = []
        total_value_matching = 0
        change_in_value = 0
        for form in self.forms:
            if 'value' in form.changed_data:
                initial_value = form.initial.get("value", 0)
                value = form.instance.value - initial_value
                form.instance.matched_to.due -= value
                form.instance.matched_to.paid += value
                self.headers.append(form.instance.matched_to)
                change_in_value += value
            total_value_matching += form.instance.value
        if self.match_by.total == 0 and self.match_by.due == 0:
            if total_value_matching != 0:
                raise forms.ValidationError(
                    _(
                        f"You are trying to match a total value of { total_value_matching }.  "
                        "Because you are entering a zero value transaction the total amount to match must be zero also."
                    ),
                    code="invalid-match"
                )
            if not self.forms:
                raise forms.ValidationError(
                    _(
                        "You are trying to enter a zero value transaction without matching to anything.  This isn't allowed because "
                        "it is pointless.",
                    ),
                    code="zero-value-transaction-not-matched"
                )
        elif self.match_by.total > 0:
            if self.forms:
                if (-1 * total_value_matching) > 0 and (-1 * total_value_matching) <= self.match_by.total:
                    self.match_by.due += change_in_value
                    self.match_by.paid -= change_in_value
                else:
                    raise forms.ValidationError(
                        _(
                            "Please ensure the total of the transactions you are matching is below the due amount."
                        ),
                        code="invalid-match"
                    )
        elif self.match_by.total < 0:
            if self.forms:
                if (-1 * total_value_matching) < 0 and (-1 * total_value_matching) >= self.match_by.total:
                    self.match_by.due += change_in_value
                    self.match_by.paid -= change_in_value
                else:
                    raise forms.ValidationError(
                        _(
                            "Please ensure the total of the transactions you are matching is below the due amount."
                        )
                    )



match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=PurchaseMatchingFormset
)

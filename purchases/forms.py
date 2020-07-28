from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.shortcuts import reverse
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField,
                                ModelChoiceIteratorWithFields)
from accountancy.forms import (AjaxForm, BaseLineFormset,
                               BaseTransactionHeaderForm, BaseTransactionMixin,
                               BaseTransactionModelFormSet, DataTableTdField,
                               Div, Field, LabelAndFieldOnly, PlainFieldErrors,
                               TableHelper)
from accountancy.helpers import delay_reverse_lazy
from accountancy.layouts import create_transaction_header_helper
from accountancy.widgets import InputDropDown
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


class PurchaseHeaderForm(BaseTransactionHeaderForm):

    class Meta:
        model = PurchaseHeader
        fields = ('supplier', 'ref', 'date', 'due_date', 'total', 'type', 'period')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # it might be tempting to change the url the form is posted to on the client
        # to include the GET parameter but this means adding a further script to
        # the edit view on the clientside because we do not reload the edit view on changing
        # the type
        
        if self.data:
            type = self.data.get(self.prefix + "-" + "type")
        else:
            type = self.initial.get('type')

        if type in self._meta.model.payment_type:
            payment_form = True
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
            if type in self._meta.model.credits:
                cleaned_data["total"] = -1 * total
        return cleaned_data


class ReadOnlyPurchaseHeaderForm(PurchaseHeaderForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.fields["type"].widget = forms.TextInput(attrs={"class": "w-100 input"})
        self.fields["supplier"].widget = forms.TextInput()
        supplier = self.fields["supplier"].queryset[0]
        self.initial["supplier"] = str(supplier)
        if self.initial.get('type') in self._meta.model.get_types_requiring_analysis(): # FIX ME - we need a global way of checking this
            # as we are repeating ourselves
            transaction_requires_analysis = True
        else:
            transaction_requires_analysis = False
        self.helper = create_transaction_header_helper(
            {
                'contact': 'supplier',
            },
            transaction_requires_analysis,
            True
        )
        # must do this afterwards
        self.initial["type"] = self.instance.get_type_display()


class PurchaseLineFormset(BaseLineFormset):

    def _construct_form(self, i, **kwargs):
        if hasattr(self, 'brought_forward'):
            kwargs["brought_forward"] = self.brought_forward
        form = super()._construct_form(i, **kwargs)
        return form

    def get_form_kwargs(self, index):
        if index is None:
            # we are getting form kwargs for new empty_form only - 
            # https://github.com/django/django/blob/master/django/forms/formsets.py
            # see method of same name
            kwargs = super().get_form_kwargs(index)
            kwargs.update({
                "brought_forward":self.brought_forward
            })
            return kwargs
        return super().get_form_kwargs(index)


    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'header')):
            return
        goods = 0
        vat = 0
        total = 0
        for form in self.forms:
            # empty_permitted = False is set on forms for existing data
            # empty_permitted = True is set new forms i.e. for non existent data
            if not form.empty_permitted or (form.empty_permitted and form.has_changed()):
                if not form.cleaned_data.get("DELETE"):
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
        if not self.header.pk:
            # IMPORTANT TO ONLY SET THIS IF WE ARE CREATING
            self.header.due = total
        
line_css_classes = {
    "Td": {
        "item": "h-100 w-100 border-0",
        "description": "can_highlight h-100 w-100 border-0",
        "nominal": "h-100 w-100 border-0",
        "goods": "can_highlight h-100 w-100 border-0",
        "vat_code": "h-100 w-100 border-0",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}

class PurchaseLineForm(AjaxForm):

    item = AjaxModelChoiceField(
        get_queryset=Item.objects.none(),
        load_queryset=Item.objects.all(),
        post_queryset=Item.objects.all(),
        inst_queryset= lambda inst : Item.objects.filter(pk=inst.item_id),
        widget=InputDropDown(
            attrs={
                "data-new": "#new_item",
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
                "data-new": "#new-nominal",
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
                "data-new": "#new-vat-code",
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
        # WHY DO WE INCLUDE THE ID?
        fields = ('id', 'item', 'description', 'goods', 'nominal', 'vat_code', 'vat',)
        ajax_fields = ('item', 'nominal', 'vat_code', ) # used in Transaction form set_querysets method

    def __init__(self, *args, **kwargs):

        column_layout_object_css_classes = {
            "Th": {},
            "Td": {}
        }

        if 'brought_forward' in kwargs:
            if brought_forward := kwargs.get('brought_forward'):
                self.brought_forward = brought_forward
                if self.brought_forward:
                    column_layout_object_css_classes["Th"]["nominal"] = "d-none"
                    column_layout_object_css_classes["Th"]["vat_code"] = "d-none"
                    column_layout_object_css_classes["Td"]["nominal"] = "d-none"
                    column_layout_object_css_classes["Td"]["vat_code"] = "d-none"
            kwargs.pop("brought_forward")

        super().__init__(*args, **kwargs)
        # if the type is a payment type we will hide the line_formset
        # on the client.
        # if the type is a brought forward type the line_formset will show
        # but the columns containing the irrelevant fields will be hidden

        self.helpers = TableHelper(
            PurchaseLineForm.Meta.fields,
            order=True,
            delete=True,
            css_classes=line_css_classes,
            column_layout_object_css_classes=column_layout_object_css_classes,
            field_layout_overrides={
                'Td': {
                    'item': PlainFieldErrors,
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                }
            }
        ).render()


class ReadOnlyPurchaseLineForm(PurchaseLineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.helpers = TableHelper(
            PurchaseLineForm.Meta.fields,
            order=False,
            delete=False,
            css_classes={
                "Td": {
                    "item": "input-disabled text-left",
                    "description": "input-disabled text-left",
                    "nominal": "input-disabled text-left",
                    "goods": "input-disabled text-left",
                    "vat_code": "input-disabled text-left",
                    "vat": "input-disabled text-left"
                }
            },
            field_layout_overrides={
                'Td': {
                    'item': PlainFieldErrors,
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                    'amount': PlainFieldErrors
                }
            },
        ).render()


enter_lines = forms.modelformset_factory(
    PurchaseLine,
    form=PurchaseLineForm, 
    formset=PurchaseLineFormset, 
    extra=5, 
    can_order=True,
    can_delete=True
)

enter_lines.include_empty_form = True

read_only_lines = forms.modelformset_factory(
    PurchaseLine,
    form=ReadOnlyPurchaseLineForm,
    formset=PurchaseLineFormset,
    extra=0,
    can_order=True,
    can_delete=True # both these keep the django crispy form template happy
    # there are of no actual use for the user
)

read_only_lines.include_empty_form = True

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
        fields = ('matched_by','matched_to', 'value', 'id') # matched_to is only needed for create
        widgets = {
            'matched_by': forms.TextInput(attrs={"readonly": True}),
            'matched_to': forms.TextInput(attrs={"readonly": True}),
        }

    def __init__(self, *args, **kwargs):

        # this logic is in case we ever need the form without the formset
        # but with a formset the keyword argument will not be passed

        if 'match_by' in kwargs:
            if match_by := kwargs.get('match_by'): # match_by could be None
                self.match_by = match_by
            kwargs.pop("match_by")

        super().__init__(*args, **kwargs)

        # # Setting the disabled attribute means even if the user tampers
        # # with the html widget django discounts the change
        # for field in self.fields:
        #     if field != "value":
        #         self.fields[field].disabled = True

        # GET request for CREATE
        if not self.data and not self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.none()
        # GET and POST requests for CREATE AND EDIT
        if self.instance.pk:
            if self.match_by.pk == self.instance.matched_to_id:
                matched_header = self.instance.matched_by
                f = -1
            else:
                matched_header = self.instance.matched_to
                f = 1
            self.fields["type"].initial = matched_header.type
            self.fields["ref"].initial = matched_header.ref
            self.fields["total"].initial = matched_header.total
            self.fields["paid"].initial = matched_header.paid
            self.fields["due"].initial = matched_header.due
            self.initial["value"] *= f
            # matched_to is a field rendered on the client because it is for the user to pick (in some situations)
            # but matched_by, although a field, can always be determined server side so we override the POST data to do so
            if self.match_by.pk:
                self.data = self.data.copy()
                # we are editing a transaction in the system
                self.data[self.prefix + "-" + "matched_by"] = self.initial.get('matched_by', self.match_by.pk)
        if not self.instance.pk and self.data:
            # creating a new transaction
            # matched_by is not required at form level therefore
            # view will attach matched_by to instance after successful validation
            self.fields["matched_by"].required = False

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
        matched_by = cleaned_data.get("matched_by")
        matched_to = cleaned_data.get("matched_to")
        value = cleaned_data.get("value")
        header = matched_to
        if self.match_by.pk:
            if self.match_by.pk == matched_to.pk:
                # matched_to could be the header we are editing
                # and if so there is no way of knowing the due amount at this point
                # as it will depend on the other matches
                # therefore postpone validation until clean method at formset level
                header = matched_by
        if header and value:
            if header.total > 0:
                if value < 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
                elif value > header.due + initial_value:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
            elif header.total < 0:
                if value > 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
                elif value < header.due + initial_value:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )


    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.matched_by = self.match_by
        if commit:
            instance.save()
        return instance



class ReadOnlyPurchaseMatchingForm(PurchaseMatchingForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True

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
                    "value": "input-disabled"
                }
            },
            field_layout_overrides={
                'Td': {
                    'type': DataTableTdField,
                    'ref': DataTableTdField,
                    'total': DataTableTdField,
                    'paid': DataTableTdField,
                    'due': DataTableTdField,
                    'value': DataTableTdField,
                }
            }
        ).render()      


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
        # when a header is being created for the first time only match records where the matched_by equals the new header are possible
        # for edits it is possible to have many matched records where the matched_by equals the header being edited AND many matched records
        # where the matched_to equals the header being edited and the matched_by is another header.  However it is not possible to
        # have many matched records of this second kind where there are many with the same matched_by header.
        overall_change_in_value = 0
        self.headers = []
        for form in self.forms:
            if not form.instance.matched_by_id or self.match_by.pk == form.instance.matched_by_id:
                # value
                if 'value' in form.changed_data:
                    initial_value = form.initial.get("value", 0)
                    value = form.instance.value - initial_value # change in value therefore
                    form.instance.matched_to.due -= value
                    form.instance.matched_to.paid += value
                    self.headers.append(form.instance.matched_to) # matched_to cannot be self.match_by here
                    overall_change_in_value += value
            else:
                # value in matched relationship is the value of the matched_to MATCHED to matched_by
                # because the matched_by here is not the header being edited we want to know the value of the
                # matched_by MATCHED to the matched_to
                # this is -1 * value
                # so here matched_to is self.match_by
                # and matched_by is another header unique among the headers in all the forms
                # this is the opposite of the above
                # self.headers will need the matched_by headers
                if 'value' in form.changed_data:
                    initial_value = form.initial.get("value", 0)
                    value = form.instance.value - initial_value
                    form.instance.value = -1 * form.instance.value
                    form.instance.matched_by.due -= value
                    form.instance.matched_by.paid += value
                    self.headers.append(form.instance.matched_by)
                    overall_change_in_value += value
        if self.match_by.total == 0 and self.match_by.due == 0:
            if overall_change_in_value != 0:
                raise forms.ValidationError(
                    _(
                        f"You are trying to match a total value of { self.match_by.paid + overall_change_in_value }.  "
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
                if (self.match_by.due + overall_change_in_value) >= 0 and (self.match_by.due + overall_change_in_value) <= self.match_by.total:
                    self.match_by.due += overall_change_in_value
                    self.match_by.paid -= overall_change_in_value
                else:
                    raise forms.ValidationError(
                        _(
                            f"Please ensure the total of the transactions you are matching is between 0 and { -1 * self.match_by.total}"
                        ),
                        code="invalid-match"
                    )
        elif self.match_by.total < 0:
            if self.forms:
                if (self.match_by.due + overall_change_in_value) <= 0 and (self.match_by.due + overall_change_in_value) >= self.match_by.total:
                    self.match_by.due += overall_change_in_value
                    self.match_by.paid -= overall_change_in_value
                else:
                    raise forms.ValidationError(
                        _(
                            f"Please ensure the total of the transactions you are matching is between 0 and {-1 * self.match_by.total}"
                        )
                    )   



match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=PurchaseMatchingFormset
)

match.include_empty_form = False

read_only_match = forms.modelformset_factory(
    PurchaseMatching,
    form=ReadOnlyPurchaseMatchingForm,
    extra=0,
    formset=PurchaseMatchingFormset
)

read_only_match.include_empty_form = False


class VoidTransaction(forms.Form):

    id = forms.IntegerField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "void-form dropdown-item pointer"
        self.helper.form_action = reverse("purchases:void")
        self.helper.form_method = "POST"
        self.helper.layout = Layout(
            Field('id', type="hidden"),
            HTML("<a class='small'>Void</a>")
        )

    def clean(self):
        try:
            self.instance = PurchaseHeader.objects.get(pk=self.cleaned_data.get("id"))
        except:
            raise forms.ValidationError(
                _(
                    "Transaction does not exist",
                    code="invalid-transaction-to-void"
                )
            )

from django import forms
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField)
from accountancy.forms import (AjaxForm, LabelAndFieldOnly, TableHelper,
                               create_tbody_helper, create_thead_helper,
                               create_transaction_header_helper)
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
        raise forms.ValidationError("test")
        

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
        # remember each of the forms is valid at this point
        # header has not been saved to DB yet
        # because obviously you don't want to do that before
        # you check the lines are all good
        if self.header.total != 0:
            total_analysed = 0
            for form in self.forms:
                # this will not do for the edit lines formset
                if form.empty_permitted and form.has_changed():
                    total_analysed = total_analysed + form.instance.amount
            if total_analysed != self.header.total:
                raise forms.ValidationError(
                    _(
                        "Total does not equal sum of values entered for each line"
                    ),
                    code="total-difference"
                )


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
                "item": "w-100 border-0",
                "description": "can_highlight w-100 border-0",
                "nominal": "w-100 border-0",
                "amount": "can_highlight w-100 border-0"
            }
        }
        self.helpers = TableHelper(
            PurchaseLineForm.Meta.fields,
            order=True,
            delete=True,
            css_classes=css_classes
        ).render()


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

    type = forms.ChoiceField(choices=PurchaseHeader.type_choices)
    ref = forms.CharField(max_length=20)
    total = forms.DecimalField(decimal_places=2, max_digits=10)
    paid = forms.DecimalField(decimal_places=2, max_digits=10)
    due = forms.DecimalField(decimal_places=2, max_digits=10)

    class Meta:
        model = PurchaseMatching
        fields = ('matched_to', 'value',)
        widgets = {
            'matched_to': forms.TextInput
        }

    def __init__(self, *args, **kwargs):
        # this logic is in case we ever need the form without the formset
        # but with a formset the keyword argument will not be passed
        if match_to := kwargs.get("match_to"):
            self.match_to = match_to
            kwargs.pop("match_to")
        super().__init__(*args, **kwargs)
        # print(self.fields["matched_to"].widget.__dict__)
        # Question - will the matched_to.pk show in the input field when editing ?
        if not self.data and not self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.none()
        elif self.instance.pk:
            self.fields["matched_to"].queryset = PurchaseHeader.objects.get(pk=self.instance.matched_to)
        self.helpers = TableHelper(
            ('type', 'ref', 'total', 'paid', 'due',) + 
            PurchaseMatchingForm.Meta.fields,
        ).render()


    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.matched_by = self.header
        if commit:
            instance.save()
        return instance



class PurchaseMatchingFormset(BaseTransactionModelFormSet):

    def __init__(self, *args, **kwargs):
        if match_to := kwargs.get("match_to"):
            self.match_to = match_to
            kwargs.pop("match_to")
        super().__init__(*args, **kwargs)


    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        try:
            form.match_to = self.match_to
        except AttributeError as e:
            pass
        return form


    def clean(self):
        super().clean()

        # type of validation depends on whether we are creating
        # or editing

        # for editing we will only receive server side those forms
        # which correspond to matchings the user has edited
        # or new matchings
        # so we have to validate based on what WAS the matching value
        # i.e. the initial value
        # and compare the change of the matching value

        # creating is simpler.  we just make sure the total of the
        # matching value does not exceed the amount due on the header

        try:
            self.match_to.pk
            # we are editing
        except e: # not sure of the exception to check so check in the shell
            # we are creating
            pass


match = forms.modelformset_factory(
    PurchaseMatching,
    form=PurchaseMatchingForm,
    extra=0,
    formset=PurchaseMatchingFormset
)

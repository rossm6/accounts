from accountancy.fields import (ModelChoiceFieldChooseIterator,
                                ModelChoiceIteratorWithFields,
                                RootAndChildrenModelChoiceIterator,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxFormMixin,
                               BaseLineFormset, BaseTransactionHeaderForm,
                               BaseTransactionLineForm,
                               BaseTransactionSearchForm)
from accountancy.helpers import Period
from accountancy.layouts import (Div, Field, LabelAndFieldAndErrors,
                                 PlainFieldErrors, TableHelper,
                                 create_journal_header_helper,
                                 create_transaction_enquiry_layout,
                                 create_transaction_header_helper)
from accountancy.widgets import SelectWithDataAttr
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from vat.models import Vat

from .models import Nominal, NominalHeader, NominalLine


class NominalForm(forms.ModelForm):

    parent = ModelChoiceFieldChooseIterator(
        label="Account Type",
        queryset=Nominal.objects.all().prefetch_related("children"),
        iterator=RootAndChildrenModelChoiceIterator
    )

    class Meta:
        model = Nominal
        fields = ('name', 'parent')

    def __init__(self, *args, **kwargs):
        if 'action' in kwargs:
            action = kwargs.pop("action")
        else:
            action = ''
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.form_action = action
        self.helper.attrs = {
            "data-form": "nominal"
        }
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors('parent', css_class="w-100"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'name', css_class="w-100 input can-highlight"),
                    css_class="mt-2"
                ),
                css_class="modal-body"
            ),
            Div(
                HTML(
                    '<button type="button" class="btn btn-sm btn-secondary cancel" data-dismiss="modal">Cancel</button>'),
                HTML('<button type="submit" class="btn btn-sm btn-success">Save</button>'),
                css_class="modal-footer"
            )
        )


class NominalHeaderForm(BaseTransactionHeaderForm):

    class Meta:
        model = NominalHeader
        fields = ('ref', 'date', 'total', 'type', 'period', 'vat_type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["total"].help_text = "<span class='d-block'>The total value of the debit side of the journal<span class='d-block'>i.e. the total of the positive values</span></span>"
        self.helper = create_journal_header_helper()

# A lot of this is common to the other modules so should be factored out


line_css_classes = {
    "Td": {
        "description": "can_highlight h-100 w-100 border-0",
        "goods": "can_highlight h-100 w-100 border-0",
        "nominal": "can_highlight input-grid-selectize-unfocussed",
        "vat_code": "can_highlight input-grid-selectize-unfocussed",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}


class NominalLineForm(BaseAjaxFormMixin, BaseTransactionLineForm):
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
        model = NominalLine
        fields = ('id', 'description', 'goods', 'nominal', 'vat_code', 'vat',)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helpers = TableHelper(
            NominalLineForm.Meta.fields,
            order=False,
            delete=True,
            css_classes=line_css_classes,
            field_layout_overrides={
                'Td': {
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                }
            }
        ).render()


class NominalLineFormset(BaseLineFormset):

    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'header')):
            return
        goods = 0
        vat = 0
        total = 0
        debits = 0
        credits = 0
        for form in self.forms:
            # empty_permitted = False is set on forms for existing data
            # empty_permitted = True is set new forms i.e. for non existent data
            if not form.empty_permitted or (form.empty_permitted and form.has_changed()):
                if not form.cleaned_data.get("DELETE"):
                    this_goods = form.instance.goods
                    this_vat = form.instance.vat
                    if this_goods > 0:
                        debits += this_goods
                        goods += this_goods
                        vat += this_vat
                    else:
                        credits += this_goods
                    if this_vat > 0:
                        debits += this_vat
                    else:
                        credits += this_vat
        if not self.header.total:
            raise forms.ValidationError(
                _(
                    "No total entered.  This should be the total value of the debit side of the journal i.e. the total of the positive values"
                ),
                code="invalid-total"
            )
        if self.header.total != debits:
            raise forms.ValidationError(
                _(
                    "The total of the debits does not equal the total you entered."
                ),
                code="invalid-total"
            )
        if debits + credits != 0:
            raise forms.ValidationError(
                _(
                    f"Debits and credits must total zero.  Total debits entered i.e. positives values entered is {debits}, "
                    f"and total credits entered i.e. negative values entered, is {credits}.  This gives a non-zero total of { debits + credits }"
                ),
                code="invalid-total"
            )
        self.header.goods = goods
        self.header.vat = vat
        self.header.total = debits


enter_lines = forms.modelformset_factory(
    NominalLine,
    form=NominalLineForm,
    formset=NominalLineFormset,
    extra=5,
    can_order=False,
    can_delete=True
)

enter_lines.include_empty_form = True


class TrialBalanceForm(forms.Form):
    from_period = forms.CharField(max_length=6)
    to_period = forms.CharField(max_length=6)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        "from_period", css_class="input"),
                    css_class="col-2"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        "to_period", css_class="input"),
                    css_class="col-2"
                ),
                css_class="row"
            ),
            Div(
                HTML("<button class='btn btn-sm btn-primary'>Report</button>"),
                css_class="text-right mt-3"
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        from_period = cleaned_data.get("from_period")
        to_period = cleaned_data.get("to_period")

        if from_period and to_period:
            from_period = Period(from_period)
            to_period = Period(to_period)
            if to_period < from_period:
                raise forms.ValidationError(
                    _(
                        "Please correct the period range so that the `to_period` is not before the `from_period`"
                    ),
                    code=f"invalid period range"
                )

        return cleaned_data


class NominalTransactionSearchForm(BaseAjaxFormMixin, BaseTransactionSearchForm):
    """
    This is not a model form.  The Meta attribute is only for the Ajax
    form implementation.
    """
    nominal = forms.ModelChoiceField(
        queryset=Nominal.objects.all(),
        widget=forms.Select(
            attrs={
                "data-load-url": reverse_lazy("nominals:load_nominals"),
                "data-selectize-type": 'nominal'
            }
        ),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = create_transaction_enquiry_layout("nominal")

    class Meta:
        # not a model form
        ajax_fields = {
            "nominal": {
                "querysets": {
                    "load": Nominal.objects.all().prefetch_related("children"),
                    "post": Nominal.objects.filter(children__isnull=True)
                },
            }
        }

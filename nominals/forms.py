from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from accountancy.fields import (AjaxModelChoiceField,
                                AjaxRootAndLeavesModelChoiceField,
                                ModelChoiceIteratorWithFields,
                                RootAndChildrenModelChoiceField,
                                RootAndLeavesModelChoiceIterator)
from accountancy.forms import (BaseAjaxForm, BaseLineFormset,
                               BaseTransactionHeaderForm,
                               BaseTransactionLineForm,
                               ReadOnlyBaseTransactionHeaderForm)
from accountancy.helpers import (delay_reverse_lazy,
                                 input_dropdown_widget_attrs_config)
from accountancy.layouts import (Div, Field, LabelAndFieldAndErrors,
                                 PlainFieldErrors, TableHelper,
                                 create_journal_header_helper,
                                 create_transaction_header_helper)
from accountancy.widgets import InputDropDown
from vat.models import Vat

from .models import Nominal, NominalHeader, NominalLine


class NominalForm(forms.ModelForm):

    parent = RootAndChildrenModelChoiceField(
        label="Account Type",
        queryset=Nominal.objects.all().prefetch_related("children"),
    )

    class Meta:
        model = Nominal
        fields = ('name', 'parent')

    def __init__(self, *args, **kwargs):
        if 'action' in kwargs:
            action = kwargs.pop("action")
        else:
            action = ''
        # we do this in QuickVatForm also so later create a new class
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
        fields = ('ref', 'date', 'total', 'type', 'period')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["total"].help_text = "<span class='d-block'>The total value of the debit side of the journal<span class='d-block'>i.e. the total of the positive values</span></span>"
        self.helper = create_journal_header_helper()


class ReadOnlyNominalHeaderForm(NominalHeaderForm):
    date = forms.DateField()  # so datepicker is not used

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.fields["type"].widget = forms.TextInput(
            attrs={"class": "w-100 input"}
        )
        self.helper = create_journal_header_helper(read_only=True)
        self.initial["type"] = self.instance.get_type_display()


line_css_classes = {
    "Td": {
        "description": "can_highlight h-100 w-100 border-0",
        "nominal": "h-100 w-100 border-0",
        "goods": "can_highlight h-100 w-100 border-0",
        "vat_code": "h-100 w-100 border-0",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}

attrs_config = input_dropdown_widget_attrs_config(
    "nominals", ["nominal", "vat_code"])
nominal_attrs, vat_code_attrs = [attrs_config[attrs] for attrs in attrs_config]


class NominalLineForm(BaseTransactionLineForm, BaseAjaxForm):

    class Meta:
        model = NominalLine
        fields = ('id', 'description', 'goods', 'nominal', 'vat_code', 'vat',)
        widgets = {
            "nominal": InputDropDown(attrs=nominal_attrs),
            "vat_code": InputDropDown(attrs=vat_code_attrs, model_attrs=['rate'])
        }
        # used in Transaction form set_querysets method
        ajax_fields = {
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


class ReadOnlyNominalLineForm(NominalLineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.helpers = TableHelper(
            NominalLineForm.Meta.fields,
            order=False,
            delete=False,
            css_classes={
                "Td": {
                    "description": "input-disabled text-left",
                    "nominal": "input-disabled text-left",
                    "goods": "input-disabled text-left",
                    "vat_code": "input-disabled text-left",
                    "vat": "input-disabled text-left"
                }
            },
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

read_only_lines = forms.modelformset_factory(
    NominalLine,
    form=ReadOnlyNominalLineForm,
    formset=NominalLineFormset,
    extra=0,
    can_order=False,
    can_delete=False
)

read_only_lines.include_empty_form = True

from accountancy.layouts import (Div, Field, LabelAndFieldAndErrors,
                                 create_transaction_enquiry_time_fields)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Field, Layout
from django import forms
from tempus_dominus.widgets import DatePicker

from .models import Vat


class VatForm(forms.ModelForm):

    class Meta:
        model = Vat
        fields = ('code', 'name', 'rate', 'registered')

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
            "data-form": "vat"
        }
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors('code', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors('name', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors('rate', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors('registered'),
                    css_class="mt-3"
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


class VatTransactionSearchForm(forms.Form):
    period = forms.CharField(
        label='Period',
        max_length=100,
        required=False
    )
    start_date = forms.DateField(
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
    end_date = forms.DateField(
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
    # used in BaseTransactionList view
    use_adv_search = forms.BooleanField(initial=False, required=False)
    # w/o this adv search is not applied

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.include_media = False
        self.helper.layout = Layout(
            Div(
                *create_transaction_enquiry_time_fields(),
                Field('use_adv_search', type="hidden"),
                css_class="form-row"
            )
        )

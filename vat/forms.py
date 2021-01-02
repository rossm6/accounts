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
                    LabelAndFieldAndErrors('code', css_class="form-control w-100"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors('name', css_class="form-control w-100"),
                    css_class="mt-2"
                ),
                Div(
                    LabelAndFieldAndErrors('rate', css_class="form-control w-100"),
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
                    '<a href="{% url \'vat:vat_list\' %}" role="button" class="btn btn-secondary cancel">Cancel</a>'
                    '<button type="submit" class="btn btn-success">Save</button>'
                ),
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
                "format": "DD-MM-YYYY"
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
                "format": "DD-MM-YYYY"
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

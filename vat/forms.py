from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, HTML
from django import forms

from accountancy.forms import Div, Field

from .models import Vat


class QuickVatForm(forms.ModelForm):

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
                    Field('code', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    Field('name', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    Field('rate', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                Div(
                    Field('registered'),
                    css_class="mt-3"
                ),
                css_class="modal-body"
            ),
            Div(
                HTML('<button type="button" class="btn btn-sm btn-secondary cancel" data-dismiss="modal">Cancel</button>'),
                HTML('<button type="submit" class="btn btn-sm btn-success">Save</button>'),
                css_class="modal-footer"
            )
        )
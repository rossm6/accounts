from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, HTML

from accountancy.fields import RootAndChildrenModelChoiceField
from accountancy.forms import Div, Field

from .models import Nominal


class NominalForm(forms.ModelForm):
    
    account_type = RootAndChildrenModelChoiceField(
        queryset=Nominal.objects.all().prefetch_related("children"),
    )

    class Meta:
        model = Nominal
        fields = ('name',)

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
                    Field('account_type', css_class="w-100"),
                    css_class="mt-2"
                ),
                Div(
                    Field('name', css_class="w-100 input"),
                    css_class="mt-2"
                ),
                css_class="modal-body"
            ),
            Div(
                HTML('<button type="button" class="btn btn-sm btn-secondary cancel" data-dismiss="modal">Cancel</button>'),
                HTML('<button type="submit" class="btn btn-sm btn-success">Save</button>'),
                css_class="modal-footer"
            )
        )
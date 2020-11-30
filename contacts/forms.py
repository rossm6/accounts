from accountancy.layouts import Div, LabelAndFieldAndErrors
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout
from django import forms

from contacts.models import Contact


class ContactForm(forms.ModelForm):
    """
    `action` is what reverse_lazy returns.  If you aren't careful,
    and deviate from below, you will get a circulate import error.

    I don't understand what is going on fully.
    """
    class Meta:
        model = Contact
        fields = ('code', 'name', 'email', 'customer', 'supplier')

    def __init__(self, *args, **kwargs):
        if (action := kwargs.get("action")) is not None:
            kwargs.pop("action")
        else:
            action = ""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_action = action
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                LabelAndFieldAndErrors(
                    'code',
                    css_class="form-control w-100"
                ),
                css_class="form-group"
            ),
            Div(
                LabelAndFieldAndErrors(
                    'name',
                    css_class="form-control w-100"
                ),
                css_class="form-group"
            ),
            Div(
                LabelAndFieldAndErrors(
                    'email',
                    css_class="form-control w-100"
                ),
                css_class="form-group"
            ),
            Div(
                LabelAndFieldAndErrors(
                    'customer',
                    css_class="mr-4"
                ),
                LabelAndFieldAndErrors(
                    'supplier',
                    css_class=""
                ),
                css_class="form-group my-4"
            ),
        )


class ModalContactForm(ContactForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.form_tag = True
        self.helper.layout = Layout(
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        'code',
                        css_class="form-control w-100"
                    ),
                    css_class="form-group"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'name',
                        css_class="form-control w-100"
                    ),
                    css_class="form-group"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'email',
                        css_class="form-control w-100"
                    ),
                    css_class="form-group"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'customer',
                        css_class="mr-4"
                    ),
                    LabelAndFieldAndErrors(
                        'supplier',
                        css_class=""
                    ),
                    css_class="form-group my-4"
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

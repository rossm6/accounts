from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import ugettext_lazy as _
from accountancy.layouts import LabelAndFieldAndErrors, Div
from crispy_forms.layout import HTML


class SignUpForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(render_value=True))
    password2 = forms.CharField(
        label='Password Confirmation', widget=forms.PasswordInput(render_value=True))

    class Meta:
        model = User
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        super().__init__( *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form-signup"
        self.helper.layout = Layout(
            HTML(
                "<h1 class='mb-4 h3 font-weight-bold'>Accounts</h1>"
            ),
            Div(
                LabelAndFieldAndErrors('username', css_class="form-control"),
                css_class="mb-3"
            ),
            Div(
                LabelAndFieldAndErrors('password1', css_class="form-control"),
                css_class="mb-3"
            ),
            Div(
                LabelAndFieldAndErrors('password2', css_class="form-control"),
                css_class="mb-3"
            ),
            Div(
                HTML('<button class="btn btn-lg btn-primary btn-block" type="submit">Sign Up</button>')
            )
        )

    def clean_password1(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get("password1")
        # Use all the validators in the settings file
        validate_password(password1)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password_1 = cleaned_data.get("password_1")
        password_2 = cleaned_data.get("password_2")
        if password_1 and password_2 and password_1 != password_2:
            raise forms.ValidationError(
                _("Passwords don't match"),
                code="unconfirmed password"
            )
        return cleaned_data

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

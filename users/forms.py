from accountancy.layouts import Div, LabelAndFieldAndErrors
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout, Submit
from django import forms
from django.contrib.auth.forms import (AuthenticationForm, PasswordResetForm,
                                       SetPasswordForm, UserCreationForm)
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _


class SignUpForm(UserCreationForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
                HTML(
                    '<button class="btn btn-lg btn-primary btn-block" type="submit">Sign Up</button>')
            )
        )


class SignInForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form-signup w-100 m-0 p-0"
        self.helper.layout = Layout(
            Div(
                LabelAndFieldAndErrors('username', css_class="form-control"),
                css_class="w-100 mb-3"
            ),
            Div(
                LabelAndFieldAndErrors('password', css_class="form-control"),
                css_class="mb-3"
            ),
            Div(
                HTML(
                    '<button class="btn btn-lg btn-success btn-block" type="submit">Sign In</button>')
            )
        )


class UserProfileForm(forms.ModelForm):
    password = forms.CharField(
        label='Password', widget=forms.PasswordInput(render_value=True))
    password2 = forms.CharField(
        label='Password Confirmation', widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Div(
                    Div(
                        HTML(
                            '<img src="http://ssl.gstatic.com/accounts/ui/avatar_2x.png" class="avatar img-circle img-thumbnail" alt="avatar">'
                        ),
                        HTML(
                            '<h6 class="my-2">Upload a different photo...</h6>'
                        ),
                        HTML(
                            '<input type="file" class="small text-center center-block file-upload">'
                        ),
                    ),
                    css_class="col-3"
                ),
                css_class="row no-gutters"
            ),
            Div(
                Div(
                    Div(
                        Div(
                            LabelAndFieldAndErrors(
                                'first_name', css_class="form-control w-100"),
                            css_class="form-group col-md-6"
                        ),
                        Div(
                            LabelAndFieldAndErrors(
                                'last_name', css_class="form-control w-100"),
                            css_class="form-group col-md-6"
                        ),
                        css_class="form-row"
                    ),
                    Div(
                        Div(
                            LabelAndFieldAndErrors(
                                'email', css_class="form-control w-100"),
                        ),
                        css_class="mb-2"
                    ),
                    Div(
                        Div(
                            LabelAndFieldAndErrors(
                                'password', css_class="form-control w-100"),
                            css_class="form-group col-md-6"
                        ),
                        Div(
                            LabelAndFieldAndErrors(
                                'password2', css_class="form-control w-100"),
                            css_class="form-group col-md-6"
                        ),
                        css_class="form-row"
                    ),
                    Div(
                        HTML(
                            "<a class='btn btn-secondary mr-2' href='{% url 'dashboard:dashboard'  %}'>Cancel</a>"
                        ),
                        Submit(
                            'Save',
                            'Save',
                            css_class="btn btn-success"
                        ),
                        css_class="d-flex justify-content-end"
                    ),
                    css_class="col"
                ),
                css_class="mt-4 row no-gutters"
            ),
        )

    def clean_password(self):
        password = self.cleaned_data.get("password")
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password2 = cleaned_data.get('password2')
        if password != self.instance.password:
            if password != password2:
                raise forms.ValidationError("Passwords don't match")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data["password"]
        if 'password' in self.changed_data:
            instance.set_password(self.cleaned_data["password"])
        if commit:
            instance.save()
        return instance


class UserPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "p-2 w-100"
        self.helper.layout = Layout(
            LabelAndFieldAndErrors('email', css_class="form-control"),
            Submit('send', 'Send', css_class="mt-3 btn btn-primary btn-lg")
        )


class UserSetPasswordForm(SetPasswordForm):
    """
        For Password Reset
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "p-2 w-100"
        self.helper.layout = Layout(
            LabelAndFieldAndErrors('new_password1', css_class="form-control"),
            LabelAndFieldAndErrors('new_password2', css_class="form-control"),
            Submit('send', 'Send', css_class="mt-3 btn btn-primary btn-lg")
        )

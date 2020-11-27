from accountancy.layouts import LabelAndFieldOnly
from accountancy.fields import (ModelChoiceIteratorWithFields,
                                ModelMultipleChoiceFieldChooseIterator)
from accountancy.layouts import (Delete, Div, LabelAndFieldAndErrors,
                                 PlainField, PlainFieldErrors, Td, Tr)
from cashbook.models import CashBook, CashBookHeader
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Fieldset, Hidden, Layout, Submit
from django import forms
from django.contrib.auth.models import ContentType, Group, Permission
from django.db.models import Q
from nominals.models import Nominal, NominalHeader
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from tempus_dominus.widgets import DatePicker
from users.forms import UserProfileForm
from vat.models import Vat, VatTransaction

from settings.layouts import TableFormset
from settings.models import FinancialYear, Period
from settings.widgets import (CheckboxSelectMultipleWithDataAttr,
                              CheckboxSelectMultipleWithDataAttr_UserEdit)

"""
Not all permissions do we want to show in the UI.

In particular we do not want the default perms django creates for models which are only parts
of transactions e.g. PurchaseHeader, PurchaseLine, PurchaseMatching etc

The queryset below is used in the edit and detail view for group and user perms.

"""

UI_PERMISSIONS = (
    Permission
    .objects
    .select_related("content_type")
    .filter(
        Q(
            content_type=ContentType.objects.get_for_model(CashBook)
        )
        |
        Q(
            Q(
                content_type=ContentType.objects.get_for_model(
                    CashBookHeader)
            )
            &
            Q(
                codename__in=[
                    perm[0]
                    for perm in CashBookHeader._meta.permissions
                ]
            )
        )
        |
        Q(
            content_type=ContentType.objects.get_for_model(Nominal)
        )
        |
        Q(
            Q(
                content_type=ContentType.objects.get_for_model(
                    NominalHeader)
            )
            &
            Q(
                codename__in=[
                    perm[0]
                    for perm in NominalHeader._meta.permissions
                ]
            )
        )
        |
        Q(
            Q(
                content_type=ContentType.objects.get_for_model(
                    PurchaseHeader)
            )
            &
            Q(
                codename__in=[
                    perm[0]
                    for perm in PurchaseHeader._meta.permissions
                ]
            )
        )
        |
        Q(
            Q(
                content_type=ContentType.objects.get_for_model(
                    SaleHeader)
            )
            &
            Q(
                codename__in=[
                    perm[0]
                    for perm in SaleHeader._meta.permissions
                ]
            )
        )
        |
        Q(
            content_type=ContentType.objects.get_for_model(Vat)
        )
        |
        Q(
            Q(
                content_type=ContentType.objects.get_for_model(
                    VatTransaction)
            )
            &
            Q(
                codename__in=[
                    perm[0]
                    for perm in VatTransaction._meta.permissions
                ]
            )
        )
    )
)


class GroupForm(forms.ModelForm):
    permissions = ModelMultipleChoiceFieldChooseIterator(
        queryset=UI_PERMISSIONS.all(),  # all is necesssary to take a copy
        widget=CheckboxSelectMultipleWithDataAttr(attrs={
            "data-option-attrs": [
                "codename",
                "content_type__app_label",
            ],
        }),
        iterator=ModelChoiceIteratorWithFields
    )

    class Meta:
        model = Group
        fields = ("permissions",)


class UserForm(UserProfileForm):
    user_permissions = ModelMultipleChoiceFieldChooseIterator(
        queryset=UI_PERMISSIONS.all(),  # all is necesssary to take a copy
        widget=CheckboxSelectMultipleWithDataAttr_UserEdit(attrs={
            "data-option-attrs": [
                "codename",
                "content_type__app_label",
            ],
        }),
        iterator=ModelChoiceIteratorWithFields
    )

    class Meta(UserProfileForm.Meta):
        fields = UserProfileForm.Meta.fields + ("groups", "user_permissions",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML(
                    "<small><span class='font-weight-bold'>Last logged in:</span> {{ user.last_login }}</small>"),
                css_class="my-3"
            ),
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        'first_name', css_class="form-control"),
                    css_class="col-6"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'last_name', css_class="form-control"),
                    css_class="col-6"
                ),
                css_class="form-row form-group"
            ),
            Div(
                Div(
                    LabelAndFieldAndErrors('email', css_class="form-control"),
                    css_class="col-12"
                ),
                css_class="form-row form-group"
            ),
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        'password', css_class="form-control"),
                    css_class="col-6"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'password2', css_class="form-control"),
                    css_class="col-6"
                ),
                css_class="form-row form-group"
            ),
            Div(
                LabelAndFieldAndErrors('groups')
            ),
            Div(
                HTML(
                    "<a class='btn btn-secondary mr-2' href='{% url 'settings:users' %}'>Cancel</a>"
                ),
                Submit(
                    'Save',
                    'Save',
                    css_class="btn btn-success"
                ),
                css_class="d-flex justify-content-end"
            ),
        )


class PeriodForm(forms.ModelForm):
    month_end = forms.DateField(
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

    class Meta:
        model = Period
        fields = ("id", "period", "month_end")
        widgets = {
            "period": forms.widgets.HiddenInput
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].required = False
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.include_media = False
        self.helper.layout = Layout(
            Div(
                PlainField(
                    'id'
                ),
                Div(
                    Div(
                        LabelAndFieldOnly('period'),
                    ),
                    css_class="bg-primary text-white col-auto col-close-icon border border-primary rounded d-flex justify-content-center align-items-center small"
                ),
                Div(
                    PlainField(
                        'month_end', css_class="w-100 form-control"),
                    css_class="col px-2"
                ),
                Div(
                    Div(
                        PlainField(
                            'DELETE', css_class="d-none col-close-icon"),
                        Delete(),
                    ),
                    css_class="pointer col-auto col-close-icon border rounded col-close-icon"
                ),
                css_class="row no-gutters p-1"
            )
        )


class PeriodFormSet(forms.BaseInlineFormSet):

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        label = form.fields["period"].label
        form.fields["period"].label = f"P{i + 1}"
        return form


FinancialYearInlineFormSetCreate = forms.inlineformset_factory(
    FinancialYear,
    Period,
    form=PeriodForm,
    formset=PeriodFormSet,
    fields=["period", "month_end"],
    extra=12,
    can_delete=True,
)


FinancialYearInlineFormSetEdit = forms.inlineformset_factory(
    FinancialYear,
    Period,
    form=PeriodForm,
    formset=PeriodFormSet,
    fields=["period", "month_end"],
    extra=0,
    can_delete=True,
)


class FinancialYearForm(forms.ModelForm):

    class Meta:
        model = FinancialYear
        fields = ("financial_year",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                LabelAndFieldAndErrors(
                    "financial_year", css_class="mt-2 form-control"),
                css_class="mb-2"
            ),
            Div(
                TableFormset(
                    [
                        {"label": "", "css_class": "d-none"},
                        "Period",
                        ""
                    ],
                    "periods"
                )
            ),
            Div(
                HTML(
                    "<button class='btn btn-primary add-period-btn'>Add Period</button>"
                ),
                css_class="my-5"
            ),
            Div(
                HTML(
                    "<a class='btn btn-secondary mr-2' href='{% url 'settings:index' %}'>Cancel</a>"
                ),
                Submit(
                    'Save',
                    'Save',
                    css_class="btn btn-success"
                ),
                css_class="mt-5 d-flex justify-content-between"
            ),
        )

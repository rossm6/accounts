from accountancy.fields import (ModelChoiceIteratorWithFields,
                                ModelMultipleChoiceFieldChooseIterator)
from accountancy.layouts import (Delete, Div, FieldAndErrors, FYInputGroup,
                                 LabelAndFieldAndErrors, LabelAndFieldOnly,
                                 PeriodInputGroup, PlainField,
                                 PlainFieldErrors, Td, Tr)
from cashbook.models import CashBook, CashBookHeader
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Fieldset, Hidden, Layout, Submit
from dateutil.relativedelta import relativedelta
from django import forms
from django.contrib.auth.models import ContentType, Group, Permission
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from nominals.models import Nominal, NominalHeader
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from tempus_dominus.widgets import DatePicker
from users.forms import UserProfileForm
from vat.models import Vat, VatTransaction

from controls.layouts import TableFormset
from controls.models import FinancialYear, Period
from controls.widgets import (CheckboxSelectMultipleWithDataAttr,
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
        iterator=ModelChoiceIteratorWithFields,
        required=False
    )

    class Meta:
        model = Group
        fields = ("name", "permissions",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                LabelAndFieldAndErrors('name', css_class="form-control w-100")
            )
        )


class UserForm(UserProfileForm):
    user_permissions = ModelMultipleChoiceFieldChooseIterator(
        queryset=UI_PERMISSIONS.all(),  # all is necesssary to take a copy
        widget=CheckboxSelectMultipleWithDataAttr_UserEdit(attrs={
            "data-option-attrs": [
                "codename",
                "content_type__app_label",
            ],
        }),
        iterator=ModelChoiceIteratorWithFields,
        required=False
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
                        'username', css_class="form-control"),
                    css_class="col-6"
                ),
                css_class="form-row form-group"
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
                    "<a class='btn btn-secondary mr-2' href='{% url 'controls:users' %}'>Cancel</a>"
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
                "format": "MM/YYYY",
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        ),
    )

    class Meta:
        model = Period
        fields = ("id", "month_end")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_show_labels = False
        self.helper.include_media = False
        self.helper.layout = Layout(
            PeriodInputGroup(
                'id',
                PlainField('month_end'),
            )
        )


FinancialYearInlineFormSetCreate = forms.inlineformset_factory(
    FinancialYear,
    Period,
    form=PeriodForm,
    fields=["period", "month_end"],
    extra=12,
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
                HTML(
                    "<button type='button' disabled class='btn btn-block btn-primary auto-fill-btn'>Auto Fill</button>"
                    "<button class='btn btn-primary add-period-btn btn-block'>Add Period</button>"
                ),
                css_class="mb-2"
            ),
            Div(
                FYInputGroup(
                    PlainField('financial_year', css_class="form-control fy")
                ),
                TableFormset(
                    [
                        {"label": "", "css_class": "d-none"},
                        "Period",
                        ""
                    ],
                    "periods"
                ),
                css_class="border-bottom"
            ),
            Div(
                Submit(
                    'Save',
                    'Create FY',
                    css_class="btn btn-success btn-block"
                ),
                css_class="mt-2 d-flex justify-content-between"
            ),
        )

    def clean_financial_year(self):
        financial_year = self.cleaned_data.get("financial_year")
        if financial_year:
            q = FinancialYear.objects.all()
            if self.instance.pk:
                q = q.exclude(pk=self.instance.pk)
            all_fys = [fy.financial_year for fy in q]
            all_fys.append(financial_year)
            all_fys.sort()
            if not(
                all(
                    all_fys[i] + 1 == all_fys[i + 1]
                    for i in range(len(all_fys) - 1)
                )
            ):
                raise forms.ValidationError(
                    _(
                        "Financial years must be consecutive.  So this financial year you are either creating or editing "
                        "must be either a year earlier than the current earliest, or a year later than the current latest."
                    ),
                    code="invalid-fy"
                )
        return financial_year

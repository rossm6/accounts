from itertools import groupby

from accountancy.fields import (ModelChoiceIteratorWithFields,
                                ModelMultipleChoiceFieldChooseIterator)
from accountancy.helpers import sort_multiple
from accountancy.layouts import (AdjustPeriod, Delete, Div, Field,
                                 FieldAndErrors, FYInputGroup,
                                 LabelAndFieldAndErrors, LabelAndFieldOnly,
                                 PeriodInputGroup, PlainField,
                                 PlainFieldErrors, Td, Tr)
from cashbook.models import CashBook, CashBookHeader
from contacts.models import Contact
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Fieldset, Hidden, Layout, Submit
from dateutil.relativedelta import relativedelta
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import ContentType, Group, Permission
from django.db.models import Case, Exists, Q, Subquery, Value, When
from django.utils.translation import ugettext_lazy as _
from nominals.models import Nominal, NominalHeader, NominalTransaction
from purchases.models import PurchaseHeader
from sales.models import SaleHeader
from tempus_dominus.widgets import DatePicker
from users.forms import UserProfileForm
from vat.models import Vat, VatTransaction

from controls.layouts import TableFormset
from controls.models import FinancialYear, ModuleSettings, Period
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
        # cashbook
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
        # contact
        Q(
            content_type=ContentType.objects.get_for_model(Contact)
        )
        |
        # financial year
        Q(
            content_type=ContentType.objects.get_for_model(FinancialYear)
        )
        |
        # groups
        Q(
            content_type=ContentType.objects.get_for_model(Group)
        )
        |
        Q(
            content_type=ContentType.objects.get_for_model(ModuleSettings)
        )
        |
        # nominal
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
        # purchases
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
        # sales
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
        # users
        Q(
            content_type=ContentType.objects.get_for_model(get_user_model())
        )
        |
        # vat
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
    month_start = forms.DateField(
        widget=DatePicker(
            options={
                "format": "MM-YYYY",
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        ),
        required=True
    )

    class Meta:
        model = Period
        fields = ("id", "month_start")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_show_labels = False
        self.helper.include_media = False
        self.helper.layout = Layout(
            PeriodInputGroup(
                'id',
                PlainField('month_start'),
            )
        )


class PeriodFormset(forms.BaseModelFormSet):
    def clean(self):
        if(any(self.errors)):
            return
        instances = [form.instance for form in self.forms]
        instances.sort(key=lambda i: i.month_start)
        for i in range(len(instances) - 1):
            if not(
                instances[i].fy.financial_year == instances[i +
                                                            1].fy.financial_year
                or
                instances[i].fy.financial_year +
                    1 == instances[i+1].fy.financial_year
            ):
                raise forms.ValidationError(
                    _(
                        f"A financial year must contain consecutive periods.  Here you selected calendar month "
                        f"{instances[i].month_start.strftime('%h %Y')} to be FY {str(instances[i].fy)} and calendar month "
                        f"{instances[i+1].month_start.strftime('%h %Y')} to be FY {str(instances[i+1].fy)}"
                    ),
                    code="invalid fy"
                )
        for fy_id, group in groupby([form.instance for form in self.forms], key=lambda i: i.fy_id):
            for i, period in enumerate(list(group), 1):
                p = str(i).rjust(2, "0")
                period.fy_and_period = str(period.fy) + p
                period.period = p


class PeriodInlineFormset(forms.BaseInlineFormSet):

    def clean(self):
        if(any(self.errors)):
            # blank forms will not have been rejected at this point
            return
        for form in self.forms:
            if form.empty_permitted and not form.has_changed():
                raise forms.ValidationError(
                    _(
                        "All periods you wish to create must have a month selected.  Delete any unwanted periods otherwise"
                    ),
                    code="invalid period"
                )
        for i in range(len(self.forms) - 1):
            if self.forms[i].instance.month_start + relativedelta(months=+1) != self.forms[i+1].instance.month_start:
                raise forms.ValidationError(
                    _(
                        "Periods must be consecutive calendar months"
                    )
                )
        # can only create.  cannot edit
        # so forms cannot relate to periods already saved
        periods = Period.objects.all()
        old_and_new = list(periods) + [form.instance for form in self.forms]
        old_and_new.sort(key=lambda p: p.month_start)
        for i in range(len(old_and_new) - 1):
            if old_and_new[i].month_start + relativedelta(months=+1) != old_and_new[i+1].month_start:
                old = old_and_new[i] if old_and_new[i].pk else old_and_new[i+1]
                new = old_and_new[i+1] if old_and_new[i].pk else old_and_new[i]
                raise forms.ValidationError(
                    _(
                        f"Period {old.period} of FY {old.fy_and_period[:4]} is for calendar month {old.month_start.strftime('%h %Y')}.  "
                        f"But you are trying to now create a period for calendar month {new.month_start.strftime('%h %Y')} again.  "
                        "This is not allowed because periods must be consecutive calendar months across ALL financial years."
                    )
                )


class AdjustFinancialYearForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = ('period', 'month_start', 'fy',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].disabled = True
        self.fields["month_start"].disabled = True
        month_start = self.initial["month_start"]
        self.fields["month_start"].label = month_start.strftime("%h %Y")
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_show_labels = False
        self.helper.disable_csrf = True
        self.helper.include_media = False
        self.helper.layout = Layout(
            Tr(
                Td(
                    PlainField('id'),
                    PlainField('period'),
                ),
                Td(
                    LabelAndFieldOnly('month_start', css_class="d-none"),
                ),
                Td(
                    FieldAndErrors('fy', css_class="w-100"),
                )
            )
        )


AdjustFinancialYearFormset = forms.modelformset_factory(
    model=Period,
    form=AdjustFinancialYearForm,
    formset=PeriodFormset,
    extra=0,
    can_delete=False,
    can_order=False
)
AdjustFinancialYearFormset.helper = FormHelper()
AdjustFinancialYearFormset.helper.template = "controls/table_formset.html"


FinancialYearInlineFormSetCreate = forms.inlineformset_factory(
    FinancialYear,
    Period,
    form=PeriodForm,
    formset=PeriodInlineFormset,
    fields=["month_start"],
    extra=12,
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
            all_fys = [fy.financial_year for fy in q]
            saved_plus_unsaved = all_fys + [financial_year]
            saved_plus_unsaved.sort()
            if not(
                all(
                    saved_plus_unsaved[i] + 1 == saved_plus_unsaved[i + 1]
                    for i in range(len(saved_plus_unsaved) - 1)
                )
            ):
                raise forms.ValidationError(
                    _(
                        f"Financial years must be consecutive.  The earliest is {all_fys[0]} and the latest is {all_fys[-1]}"
                    ),
                    code="invalid-fy"
                )
        return financial_year


class ModuleSettingsForm(forms.ModelForm):
    """
    See notes on ModuleSettings model
    """

    class Meta:
        model = ModuleSettings
        fields = ("cash_book_period", "nominals_period",
                  "purchases_period", "sales_period")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        """
        You cannot post into a period in a FY which has been finalised.
        """
        t = NominalTransaction.objects.filter(module="NL").filter(type="nbf").values(
            "period__fy_and_period").order_by("-period__fy_and_period")
        w = When(Exists(t), then=t[:1])
        q = (
            Period.objects.filter(
                fy_and_period__gte=(
                    Period.objects.annotate(
                        earliest_period=(
                            Case(w, default=Value("000000"))
                        )
                    ).values('earliest_period')[:1]
                )
            )
        )
        for field in self.fields:
            q = q.all()
            self.fields[field].queryset = q
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML(
                "<h1 class='font-weight-bold h5'>Module Settings</h1>",
            ),
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        'cash_book_period', css_class="w-100"),
                    css_class="my-1 col-12"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'nominals_period', css_class="w-100"),
                    css_class="my-1 col-12"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'purchases_period', css_class="w-100"),
                    css_class="my-1 col-12"
                ),
                Div(
                    LabelAndFieldAndErrors('sales_period', css_class="w-100"),
                    css_class="my-1 col-12"
                ),
                css_class="row"
            ),
            Submit("save", "Save", css_class="mt-3")
        )

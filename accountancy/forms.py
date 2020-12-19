from django.template.loader import render_to_string
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout
from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from accountancy.fields import UIDecimalField
from accountancy.models import MatchedHeaders

from .layouts import (AdvSearchField, DataTableTdField, Draggable, Label,
                      LabelAndFieldAndErrors, PlainField, PlainFieldErrors,
                      TableHelper, Td, Th, Tr,
                      create_transaction_header_helper)


class BaseAjaxFormMixin:
    """

    AJAX is obviously recommended if the total choices is very high for any field
    in a form.

    This class just sets the different querysets needed depending on whether
    the form is new, for an instance, or data is being posted.  In addition
    it always also sets the queryset to be used by remote AJAX calls.

    It only supports foreign key model choices at the moment ...

    WARNING - The iterator cannot be set at this stage after form initialisation.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fields = self.Meta.ajax_fields
        for field in fields:
            field_model = self.fields[field].queryset.model
            querysets = {
                "get": field_model.objects.none(),
                "load": field_model.objects.all(),
                "post": field_model.objects.all(),
                "instance": lambda pk: field_model.objects.filter(pk=pk),
            }
            querysets.update(
                fields[field].get("querysets", {})
            )
            if self.data:
                queryset = querysets["post"]
            elif hasattr(self.Meta, "model") and self.instance.pk:
                field_value_from_instance = getattr(
                    self.instance, f"{field}_{field_model._meta.pk.name}")
                queryset = querysets["instance"](field_value_from_instance)
            else:
                queryset = querysets["get"]
            self.fields[field].queryset = queryset
            self.fields[field].load_queryset = querysets["load"]
            # We need this to validate inputs for the input dropdown widget
            self.fields[field].post_queryset = querysets["post"]
            if searchable_fields := fields[field].get('searchable_fields'):
                self.fields[field].searchable_fields = searchable_fields
            self.fields[field].empty_label = fields[field].get(
                "empty_label", None)

    def full_clean(self):
        """
        Override the choices so that only the chosen is included
        """
        super().full_clean()  # clean all of self.data and populate self._errors and self.cleaned_data
        if hasattr(self, "cleaned_data"):
            ajax_fields = self.Meta.ajax_fields
            for field in ajax_fields:
                if chosen := self.cleaned_data.get(field):
                    iterator = self.fields[field].iterator
                    if isinstance(iterator, type):
                        iterator = iterator(self.fields[field])
                        self.fields[field].iterator = iterator
                    choice_for_ui = self.fields[field].iterator.choice(
                        chosen)  # e.g. (value, label)
                    self.fields[field].choices = [choice_for_ui]
                else:
                    self.fields[field].choices = [
                        (None, (self.fields[field].empty_label or ""))]


class BaseTransactionMixin:
    """
    This mixin ensures that the correct sign is showed in the UI by using the ui_<field_name> attribute of the model instance.
    """

    def __init__(self, *args, **kwargs):
        _initial = {}
        if instance := kwargs.get("instance"):
            for field in self._meta.fields:
                model_field = instance._meta.get_field(field)
                if isinstance(model_field, UIDecimalField):
                    _initial[field] = getattr(instance, "ui_" + field)
        if initial := kwargs.get("initial"):
            # initial passed to model form should override our _initial
            _initial.update(initial)
        elif _initial:
            kwargs["initial"] = _initial
        super().__init__(*args, **kwargs)


class BaseTransactionSearchForm(forms.Form):
    reference = forms.CharField(
        label='Reference',
        max_length=100,
        required=False
    )
    total = forms.DecimalField(
        label='Total',
        required=False
    )

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
    include_voided = forms.BooleanField(
        label="Include Voided Transactions", initial=False, required=False)
    # used in BaseTransactionList view
    use_adv_search = forms.BooleanField(initial=True, required=False)
    # w/o this adv search is not applied
    # clientside this should be set to true always
    # originally i assumed a difference between the default query executed
    # when the page loads and a blank adv search form.  now i do not so
    # this might as well always be set.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.include_media = False


class SalesAndPurchaseTransactionSearchForm(BaseTransactionSearchForm):
    # subclass must define a contact model choice field
    search_within = forms.ChoiceField(
        choices=(
            ('any', 'Any'),
            ('tran', 'Transaction date'),
            ('due', 'Due Date')
        )
    )


class BaseTransactionHeaderForm(BaseTransactionMixin, forms.ModelForm):

    date = forms.DateField(
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
        )
    )
    due_date = forms.DateField(
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # VERY IMPORTANT USERS CANNOT CHANGE THE TYPE ONCE A TRANSACTION
            # HAS BEEN CREATED
            # Form will validate if they do change it but save will not reflect change.
            self.fields["type"].disabled = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data["total"] == instance.total:
            """
            We need to flip the sign entered into the form field if the transaction is 
            a negative transaction.

            Often in Django though, as is done in all the views, one wants to save the model form 
            to get the instance without hitting the db yet.  Without this check between instance.total and
            the total within the cleaned data, we'd reverse the following change each time we called save.
            """
            instance.ui_total = instance.total
            """
            I tried putting the logic inside ui_total just into total but this causes Django to refresh 
            the instance from the db which falls over.  So this is necessary -

                instance.ui = instance.total

            Where,

                instance.total is from self.cleaned_data["total"] i.e. value entered into UI form
                instance.ui_total takes this value and flips the sign ready for saving to DB

            """
            instance.due = instance.total - instance.paid
        if commit:
            instance.save()
        return instance


class SaleAndPurchaseHeaderFormMixin:
    def __init__(self, *args, **kwargs):
        contact_model_name = kwargs.pop("contact_model_name")
        super().__init__(*args, **kwargs)
        if self.data:
            tran_type = self.data.get(self.prefix + "-" + "type")
        else:
            tran_type = self.initial.get('type')

        if tran_type in self._meta.model.payment_types:
            payment_form = True
            if tran_type in self._meta.model.get_types_requiring_analysis():
                payment_brought_forward_form = False
                self.fields["cash_book"].required = True
            else:
                payment_brought_forward_form = True
        else:
            payment_brought_forward_form = False
            payment_form = False
        self.helper = create_transaction_header_helper(
            {
                'contact': contact_model_name,
            },
            payment_form=payment_form,
            payment_brought_forward_form=payment_brought_forward_form
        )


class BaseTransactionModelFormSet(forms.BaseModelFormSet):

    def get_ordering_widget(self):
        return forms.HiddenInput(attrs={'class': 'ordering'})


class BaseTransactionLineForm(BaseTransactionMixin, forms.ModelForm):

    def clean(self):
        cleaned_data = super().clean()
        goods = cleaned_data.get("goods")
        vat = cleaned_data.get("vat")
        if goods == 0 and vat == 0:
            raise forms.ValidationError(
                _(
                    "Goods and Vat cannot both be zero."
                ),
                code="zero-value-line"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
        return instance


class BaseLineFormset(BaseTransactionModelFormSet):

    def __init__(self, *args, **kwargs):
        """
        header is the header object e.g. PurchaseHeader instance
        brought_forward is just a boolean flag
        """
        if 'header' in kwargs:
            if header := kwargs.get('header'):  # header could be None
                self.header = header
            kwargs.pop("header")
        if 'brought_forward' in kwargs:
            brought_forward = kwargs.get('brought_forward')
            self.brought_forward = brought_forward
            kwargs.pop("brought_forward")
        super().__init__(*args, **kwargs)


class SaleAndPurchaseLineFormset(BaseLineFormset):
    def _construct_form(self, i, **kwargs):
        if hasattr(self, 'brought_forward'):
            kwargs["brought_forward"] = self.brought_forward
        if hasattr(self, 'header'):
            kwargs["header"] = self.header
        form = super()._construct_form(i, **kwargs)
        return form

    def get_form_kwargs(self, index):
        if index is None:
            # we are getting form kwargs for new empty_form only -
            # https://github.com/django/django/blob/master/django/forms/formsets.py
            # see method of same name
            kwargs = super().get_form_kwargs(index)
            kwargs.update({
                "brought_forward": self.brought_forward,
            })
            return kwargs
        return super().get_form_kwargs(index)

    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'header')):
            return
        goods = 0
        vat = 0
        for form in self.forms:
            # empty_permitted = False is set on forms for existing data
            # empty_permitted = True is set new forms i.e. for non existent data
            if not form.empty_permitted or (form.empty_permitted and form.has_changed()):
                if not form.cleaned_data.get("DELETE"):
                    form.instance.type = self.header.type
                    # The type is actually reassigned in accountancy.views.RESTBaseCreateTransactionMixin
                    # But we need to it here early so that the ui_goods and ui_vat descriptor logic works
                    # We can't remove the assignment in the aforementioned view because the nominal app relies on this
                    form.instance.ui_goods = form.instance.goods
                    form.instance.ui_vat = form.instance.vat
                    goods += form.instance.goods
                    vat += form.instance.vat
        total = goods + vat
        if self.header.total != 0 and self.header.total != total:
            raise forms.ValidationError(
                _(
                    "The total of the lines does not equal the total you entered."
                ),
                code="invalid-total"
            )
        self.header.goods = goods
        self.header.vat = vat
        self.header.total = total
        self.header.due = self.header.total - self.header.paid


line_css_classes = {
    "Td": {
        "description": "can_highlight h-100 w-100 form-control border-0",
        "goods": "can_highlight h-100 w-100 form-control border-0",
        "nominal": "can_highlight input-grid-selectize-unfocussed form-control border-0 ",
        "vat_code": "can_highlight input-grid-selectize-unfocussed form-control border-0",
        "vat": "can_highlight w-100 h-100 form-control border-0"
    }
}


class BroughtForwardLineForm(BaseAjaxFormMixin, BaseTransactionLineForm):

    def __init__(self, *args, **kwargs):

        self.column_layout_object_css_classes = {
            "Th": {},
            "Td": {}
        }

        if 'brought_forward' in kwargs:
            brought_forward = kwargs.get('brought_forward')
            self.brought_forward = brought_forward
            if self.brought_forward:
                self.column_layout_object_css_classes["Th"]["nominal"] = "d-none"
                self.column_layout_object_css_classes["Th"]["vat_code"] = "d-none"
                self.column_layout_object_css_classes["Td"]["nominal"] = "d-none"
                self.column_layout_object_css_classes["Td"]["vat_code"] = "d-none"
            kwargs.pop("brought_forward")

        if 'header' in kwargs:
            header = kwargs.get('header')
            self.header = header
            kwargs.pop("header")

        super().__init__(*args, **kwargs)

        if hasattr(self, 'brought_forward') and self.brought_forward:
            self.fields["nominal"].required = False
            self.fields["vat_code"].required = False
        # if the type is a payment type we will hide the line_formset
        # on the client.
        # if the type is a brought forward type the line_formset will show
        # but the columns containing the irrelevant fields will be hidden


# WHEN WE DELETE THE ITEM FIELD WE'LL HAVE THE SAME LINE FORM
# FOR SALES, PURCHASES, CASH BOOK

class BaseCashBookLineForm(BroughtForwardLineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helpers = TableHelper(
            self._meta.fields,
            order=True,
            delete=True,
            css_classes=line_css_classes,
            column_layout_object_css_classes=self.column_layout_object_css_classes,
            field_layout_overrides={
                'Td': {
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                }
            }
        ).render()


class SaleAndPurchaseLineForm(BroughtForwardLineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, 'brought_forward') and self.brought_forward:
            pass

        self.helpers = TableHelper(
            self._meta.fields,
            order=True,
            delete=True,
            css_classes=line_css_classes,
            column_layout_object_css_classes=self.column_layout_object_css_classes,
        ).render()


class SaleAndPurchaseMatchingForm(forms.ModelForm):
    """

    When creating new transactions there is the option to match
    the new transaction to existing transactions.  This form will
    therefore have to be built on the client dynamically for creating
    new transactions.

    CAUTION -

    The type field needs the label overriding to the display
    name of the value.  This is easy when we have an instance;
    if the submitted form though is for a new instance we
    have to get the label based on the cleaned user input.  This
    is done in clean.  Type is defined on the base class.

    """

    ref = forms.CharField(
        max_length=20, widget=forms.TextInput(attrs={"readonly": True}))
    total = forms.DecimalField(
        decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={"readonly": True}))
    paid = forms.DecimalField(decimal_places=2, max_digits=10,
                              widget=forms.NumberInput(attrs={"readonly": True}))
    due = forms.DecimalField(decimal_places=2, max_digits=10,
                             widget=forms.NumberInput(attrs={"readonly": True}))

    class Meta:
        fields = ('matched_by', 'matched_to', 'value', 'id')
        widgets = {
            'matched_by': forms.TextInput(attrs={"readonly": True}),
            'matched_to': forms.TextInput(attrs={"readonly": True}),
        }

    def __init__(self, *args, **kwargs):
        # this logic is in case we ever need the form without the formset
        # but with a formset the keyword argument will not be passed
        if 'tran_being_created_or_edited' in kwargs:
            # match_by could be None
            if tran_being_created_or_edited := kwargs.get('tran_being_created_or_edited'):
                self.tran_being_created_or_edited = tran_being_created_or_edited
            kwargs.pop("tran_being_created_or_edited")
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            # GET and POST requests for creating a match
            self.fields["matched_by"].required = False
        else:
            # GET and POST requests for editing a match
            self.fields["matched_by"].disabled = True
            self.fields["matched_to"].disabled = True
            ui_match = self.Meta.model.show_match_in_UI(
                tran_being_created_or_edited, self.instance)
            self.fields["type"].initial = ui_match["type"]
            self.fields["ref"].initial = ui_match["ref"]
            self.fields["total"].initial = ui_match["total"]
            self.fields["paid"].initial = ui_match["paid"]
            self.fields["due"].initial = ui_match["due"]
            self.initial["value"] = ui_match["value"]

        self.helpers = TableHelper(
            ('type', 'ref', 'total', 'paid', 'due',) +
            self._meta.fields,
            css_classes={
                "Td": {
                    "type": "input-disabled",
                    "ref": "input-disabled",
                    "total": "input-disabled",
                    "paid": "input-disabled",
                    "due": "input-disabled",
                    "value": "w-100 h-100 border-0 pl-2"
                }
            },
            field_layout_overrides={
                'Td': {
                    'type': DataTableTdField,
                    'ref': DataTableTdField,
                    'total': DataTableTdField,
                    'paid': DataTableTdField,
                    'due': DataTableTdField,
                    'value': PlainFieldErrors,
                }
            }
        ).render()

    def clean(self):
        cleaned_data = super().clean()
        matched_by = cleaned_data.get("matched_by")
        matched_to = cleaned_data.get("matched_to")
        ui_initial_value = self.initial.get("value") or 0
        ui_value = cleaned_data.get("value")
        header = None
        tran_being_created_or_edited_is_matched_by = True
        # check transaction exists as attribute first because it will not if the header_form fails
        if hasattr(self, 'tran_being_created_or_edited'):
            if not self.instance.pk:
                # this is a new match so we need to check matched_to can be adjusted by new match value
                tran_being_created_or_edited_is_matched_by = True
                header = matched_to
                self.initial_value = initial_value = 0
                if (self.tran_being_created_or_edited.pk
                        and self.tran_being_created_or_edited.pk == matched_to.pk):
                    raise forms.ValidationError(
                        _(
                            "Cannot match a transaction to itself."
                        ),
                        code="invalid-match"
                    )
            else:
                if self.tran_being_created_or_edited.pk == self.instance.matched_by_id:
                    tran_being_created_or_edited_is_matched_by = True
                    header = matched_to
                else:
                    tran_being_created_or_edited_is_matched_by = False
                    header = matched_by
                self.initial_value = initial_value = self.Meta.model.ui_match_value(
                    header, ui_initial_value)
        else:
            return  # header_form must have failed so do not bother checking anything further
        # convert ui_value to the value to be checked against the header
        # e.g. credit note of 120.00 has ui_value of 120.00
        # value here would be -120.00
        # header.total would be -120.00
        value = self.Meta.model.ui_match_value(header, ui_value)
        if header:
            if header.is_void():
                raise forms.ValidationError(
                    _(
                        "Cannot match to a void transaction"
                    ),
                    code="invalid-match"
                )



            value_change = (value - initial_value)
            due_would_be = header.due - value_change
            f = -1 if header.is_negative_type() else 1
            if header.total > 0:
                # change initial value just for logic.  do not save this
                # see test -
                # purchases.testing.test_integration.test_matching.EditTransactionMatching.test_decrease_match_value_legal_31
                initial_value_1 = -1 * initial_value if initial_value < 0 else initial_value
            elif header.total < 0:
                # change initial value just for logic.  do not save this
                initial_value_1 = -1 * initial_value if initial_value > 0 else initial_value
            else:
                self.add_error(
                    "value",
                    forms.ValidationError(
                        _(
                            "You are trying to match a transaction which has a total of zero.  This is disallowed always because it should "
                            "be fully matched already."
                        ),
                        code="invalid match"
                    )
                )
            if (
                (
                    header.total > 0
                    and
                    not (due_would_be >= 0 and due_would_be <= header.due +
                         initial_value_1 and due_would_be <= header.total)
                )
                or
                (
                    header.total < 0
                    and
                    not (due_would_be <= 0 and due_would_be >= header.due +
                         initial_value_1 and due_would_be >= header.total)
                )
            ):
                if header.due + initial_value_1 == 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                "This transaction is not outstanding."
                            ),
                            code="invalid match"
                        )
                    )
                else:
                    if tran_being_created_or_edited_is_matched_by:
                        # due_would_be can be zero
                        # due_would_be can be header.due + initial_value_1
                        # due_would_be can be any value in between because still less than or equal to total
                        # due_would_be = header.due - value + initial_value
                        # so solve these -
                        # header.due - value + initial_value = 0
                        # header.due - value + initial_value = header.due + initial_value_1
                        lower = header.due + initial_value
                        upper = initial_value - initial_value_1
                        lower *= f
                        if lower == 0:
                            lower = 0  # avoid negative zero
                        upper *= f
                        if upper == 0:
                            upper = 0  # avoid negative zero
                        if lower > upper:
                            t = lower
                            lower = upper
                            upper = t
                        self.add_error(
                            "value",
                            forms.ValidationError(
                                _(
                                    f"Value must be between {lower} and {upper}"
                                ),
                                code="invalid match"
                            )
                        )
                    else:
                        self.add_error(
                            "value",
                            forms.ValidationError(
                                _(
                                    f'Not allowed because it would mean a due of {f * due_would_be} for this transaction when the total is {f * header.total}'
                                ),
                                code="invalid match"
                            )
                        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            instance.matched_by = self.tran_being_created_or_edited
        if commit:
            instance.save()
        return instance


class SaleAndPurchaseMatchingFormset(BaseTransactionModelFormSet):

    """

    Match by has two meaning depending on the context.

    For create, match by is the header record which is being used to match
    the other headers against -

        E.g.

        The user creates a new receipt for value -100.00
        And they select to match an invoice against this in the same posting.

        In this situation the receipt is the "match_by" header and the
        "match_to" header is the invoice.

    For edit, match by is the header record we are viewing to edit.
    In terms of the matching record itself, this header could correspond
    to either the matching_by or the matching_to.

    """

    def __init__(self, *args, **kwargs):
        if 'match_by' in kwargs:
            if match_by := kwargs.get('match_by'):  # match_by could be None
                self.tran_being_created_or_edited = match_by
            kwargs.pop("match_by")
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        if hasattr(self, 'tran_being_created_or_edited'):
            kwargs["tran_being_created_or_edited"] = self.tran_being_created_or_edited
        form = super()._construct_form(i, **kwargs)
        return form

    def get_header_details_for_match_form(self, form):
        # form.instance.value should always be the value of the matched_to
        # here we want the value which relates to self.tran_being_created_or_edited
        if not form.instance.matched_by_id or self.tran_being_created_or_edited.pk == form.instance.matched_by_id:
            value = -1 * form.instance.value
            t = form.instance.matched_to.get_type_display()
            ref = form.instance.matched_to.ref
        else:
            value = form.instance.value
            t = form.instance.matched_by.get_type_display()
            ref = form.instance.matched_by.ref
        value = MatchedHeaders.ui_match_value(
            self.tran_being_created_or_edited, value)
        return {
            "type": t,
            "ref": ref,
            "value": value
        }

    def create_html_for_error_when_total_matched_to_value_is_non_zero(self, positive_tran, total_matched_to_value, total_matched_by_value):
        matched_to_forms = []
        matched_by_forms = []
        header = self.tran_being_created_or_edited
        for form in self.forms:
            if not form.instance.matched_by_id or self.tran_being_created_or_edited.pk == form.instance.matched_by_id:
                matched_by_forms.append(form)
            else:
                matched_to_forms.append(form)
        headers_from_matched_to_forms = [
            self.get_header_details_for_match_form(form) for form in matched_to_forms]
        headers_from_matched_by_forms = [
            self.get_header_details_for_match_form(form) for form in matched_by_forms]
        html_string = render_to_string("accountancy/non_field_matching_error.html", {
            "total_matched_to_value_ui": positive_tran * total_matched_to_value,
            "headers_from_matched_to_forms": headers_from_matched_to_forms,
            "headers_from_matched_by_forms": headers_from_matched_by_forms,
            "main_header_due_ui": positive_tran * header.due,
            "total_matched_by_value_ui": positive_tran * total_matched_by_value,
        })
        return forms.ValidationError(
            _(mark_safe(html_string)),
            code="invalid-match"
        )

    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'tran_being_created_or_edited')):
            return
        # undo the effects of matching to date
        self.tran_being_created_or_edited.due = self.tran_being_created_or_edited.total
        self.tran_being_created_or_edited.paid = 0
        # sum of values where header being created or edited is the matched_by in the match
        total_matched_by_value = 0
        # sum of values where header being created or edited is the matched_to in the match
        total_matched_to_value = 0
        self.headers = []
        for form in self.forms:
            initial_value = form.initial_value  # note this is added during form.clean
            # it is the ui initial_value already converted to the initial_value we need
            ui_value = form.instance.value
            if not form.instance.matched_by_id or self.tran_being_created_or_edited.pk == form.instance.matched_by_id:
                header_to_update = form.instance.matched_to
                value = MatchedHeaders.ui_match_value(
                    header_to_update, ui_value)
                diff = value - initial_value
                header_to_update.due -= diff
                header_to_update.paid += diff
                form.instance.value = value
                total_matched_by_value += (-1 * value)
            else:
                header_to_update = form.instance.matched_by
                value = MatchedHeaders.ui_match_value(
                    header_to_update, ui_value)
                diff = value - initial_value
                header_to_update.due -= diff
                header_to_update.paid += diff
                value = value * -1
                form.instance.value = value
                total_matched_to_value += value
            self.headers.append(header_to_update)
        f = -1 if self.tran_being_created_or_edited.is_negative_type() else 1
        if self.tran_being_created_or_edited.total == 0:
            if total_matched_by_value + total_matched_to_value != 0:
                raise forms.ValidationError(
                    _(
                        f"You are trying to match a total value of { -1 * (total_matched_by_value + total_matched_to_value) }.  "
                        "Because you are entering a zero value transaction the total amount to match must be zero also."
                    ),
                    code="invalid-match"
                )
            if not self.forms:
                raise forms.ValidationError(
                    _(
                        "You are trying to enter a zero value transaction without matching to anything.  This isn't allowed because "
                        "it is pointless.",
                    ),
                    code="zero-value-transaction-not-matched"
                )
        elif self.tran_being_created_or_edited.total > 0:
            if self.forms:
                self.tran_being_created_or_edited.due -= total_matched_to_value
                if (
                    self.tran_being_created_or_edited.due - total_matched_by_value >= 0
                    and
                    self.tran_being_created_or_edited.due -
                        total_matched_by_value <= self.tran_being_created_or_edited.due
                ):
                    self.tran_being_created_or_edited.due -= total_matched_by_value
                    self.tran_being_created_or_edited.paid += (
                        total_matched_by_value + total_matched_to_value)
                else:
                    if total_matched_to_value == 0:
                        raise forms.ValidationError(
                            _(
                                f"Please ensure the total of the transactions you are matching is between 0 and { self.tran_being_created_or_edited.total }"
                            ),
                            code="invalid-match"
                        )
                    else:
                        raise self.create_html_for_error_when_total_matched_to_value_is_non_zero(
                            f, total_matched_to_value, total_matched_by_value)
        elif self.tran_being_created_or_edited.total < 0:
            if self.forms:
                self.tran_being_created_or_edited.due -= total_matched_to_value
                if (
                    self.tran_being_created_or_edited.due - total_matched_by_value <= 0
                    and
                    self.tran_being_created_or_edited.due -
                        total_matched_by_value >= self.tran_being_created_or_edited.due
                ):
                    self.tran_being_created_or_edited.due -= total_matched_by_value
                    self.tran_being_created_or_edited.paid += (
                        total_matched_by_value + total_matched_to_value)
                else:
                    if total_matched_to_value == 0:
                        raise forms.ValidationError(
                            _(
                                f"Please ensure the total of the transactions you are matching is between 0 and { self.tran_being_created_or_edited.total }"
                            ),
                            code="invalid-match"
                        )
                    else:
                        raise self.create_html_for_error_when_total_matched_to_value_is_non_zero(
                            f, total_matched_to_value, total_matched_by_value)


class BaseVoidTransactionForm(forms.Form):

    id = forms.IntegerField()

    def __init__(self, header_model, form_action, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_model = header_model
        self.helper = FormHelper()
        self.helper.form_class = "void-form dropdown-item pointer"
        self.helper.form_action = form_action
        self.helper.form_method = "POST"
        self.helper.layout = Layout(
            Field('id', type="hidden"),
            HTML("<a class='small'>Void</a>")
        )

    def clean(self):
        try:
            self.instance = self.header_model.objects.select_for_update().exclude(status="v").get(
                pk=self.cleaned_data.get("id"))
        except:
            raise forms.ValidationError(
                _(
                    "Could not find transaction to void.  "
                    "If it has not been voided already, please try again later",
                ),
                code="invalid-transaction-to-void"
            )


def aged_matching_report_factory(
        contact_model,
        contact_creation_url,
        contact_load_url):
    """
    Creates a form for AgedCreditor and AgedDebtor report
    """

    contact_field_name = contact_model.__name__.lower()
    from_contact_field = "from_" + contact_field_name
    to_contact_field = "to_" + contact_field_name

    class Form(forms.Form):
        period = forms.CharField(max_length=6)
        show_transactions = forms.BooleanField(required=False)
        adv_search_form = forms.BooleanField(required=True, initial=True)

        def set_none_queryset_for_fields(self, fields):
            for field in fields:
                self.fields[field].queryset = self.fields[field].queryset.none()

        def clean(self):
            cleaned_data = super().clean()
            if (
                (to_contact := cleaned_data.get(to_contact_field)) and
                (from_contact := cleaned_data.get(from_contact_field))
                and to_contact.pk < from_contact.pk
            ):
                raise forms.ValidationError(
                    _(
                        f"This is not a valid range for {contact_field_name}s "
                        f"because the second {contact_field_name} you choose comes before the first {contact_field_name}"
                    ),
                    code=f"invalid {contact_field_name} range"
                )

            return cleaned_data

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # dynamically set the contact range fields
            # it will not work if you assign the form field to a variable
            # and use for both fields.  I didn't try a deep copy.

            self.fields[from_contact_field] = forms.ModelChoiceField(
                queryset=contact_model.objects.all(),
                required=False,
                widget=forms.Select(attrs={
                    "data-form": contact_field_name,
                    "data-form-field": contact_field_name + "-code",
                    "data-creation-url": contact_creation_url,
                    "data-load-url": contact_load_url,
                    "data-contact-field": True
                }))

            self.fields[to_contact_field] = forms.ModelChoiceField(
                queryset=contact_model.objects.all(),
                required=False,
                widget=forms.Select(attrs={
                    "data-form": contact_field_name,
                    "data-form-field": contact_field_name + "-code",
                    "data-creation-url": contact_creation_url,
                    "data-load-url": contact_load_url,
                    "data-contact-field": True
                }))

            if not self.data:
                # ajax form mixin form not work here so we do this
                self.set_none_queryset_for_fields(
                    [from_contact_field, to_contact_field])

            self.helper = FormHelper()
            self.helper.form_method = "GET"
            self.helper.layout = Layout(
                Div(
                    Div(
                        LabelAndFieldAndErrors(
                            from_contact_field, css_class="w-100"),
                        css_class="col"
                    ),
                    Div(
                        LabelAndFieldAndErrors(
                            to_contact_field, css_class="w-100"),
                        css_class="col"
                    ),
                    Div(
                        LabelAndFieldAndErrors(
                            "period", css_class="w-100"),
                        css_class="col"
                    ),
                    css_class="row"
                ),
                Div(
                    Div(
                        LabelAndFieldAndErrors(
                            "show_transactions", css_class=""),
                        css_class="col"
                    ),
                    Hidden('adv_search_form', True),
                    css_class="mt-4 row"
                ),
                Div(
                    HTML("<button class='btn btn-sm btn-primary'>Report</button>"),
                    css_class="text-right mt-3"
                )
            )

    return Form

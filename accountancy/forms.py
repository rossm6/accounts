from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout
from django import forms
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

from .layouts import (AdvSearchField, DataTableTdField, Draggable, Label,
                      LabelAndFieldAndErrors, PlainField, PlainFieldErrors,
                      TableHelper, Td, Th, Tr,
                      create_transaction_header_helper)


class BaseAjaxForm(forms.ModelForm):

    """

    AJAX is obviously recommended if the total choices is very high for any field
    in a form.

    This class just sets the different querysets needed depending on whether
    the form is new, for an instance, or data is being posted.  In addition
    it always also sets the queryset to be used by remote AJAX calls.

    It only supports foreign key model choices at the moment ...

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_model = self.Meta.model
        fields = self.Meta.ajax_fields
        for field in fields:
            field_model = form_model._meta.get_field(field).related_model
            pk_field_name = field + "_id"  # THIS WILL DO FOR NOW BUT THIS ISN'T ALWAYS THE CASE
            # 'to_field' could have different name other than "id"
            querysets = {
                "get": field_model.objects.none(),
                "load": field_model.objects.all(),
                "post": field_model.objects.all(),
                "instance": lambda pk: field_model.objects.filter(pk=pk),
            }
            querysets.update(fields[field].get("querysets", {}))
            if self.data:
                queryset = querysets["post"]
            elif self.instance.pk:
                queryset = querysets["instance"](
                    getattr(self.instance, pk_field_name))
            else:
                queryset = querysets["get"]
            self.fields[field].queryset = queryset
            self.fields[field].load_queryset = querysets["load"]
            # We need this to validate inputs for the input dropdown widget
            self.fields[field].post_queryset = querysets["post"]
            if iterator := fields[field].get('iterator'):
                self.fields[field].iterator = iterator
            if searchable_fields := fields[field].get('searchable_fields'):
                self.fields[field].searchable_fields = searchable_fields
            self.fields[field].empty_label = fields[field].get(
                "empty_label", None)


class BaseTransactionMixin:

    """

    At least this is needed ...

        Accountancy forms should give the user the option to enter a positive number
        which is then understand by the system as a negative number i.e. a credit balance

        For example when entering a payment it is more intuitive to type 100.00
        but this needs to be saved in the database as -100.00, because it is a credit balance

        If the user is creating data there is no problem.  But if they are editing data they
        need to see this negative value as a positive.

        So we need a global dictionary of transaction types and the associated debit or credit.
        And then we just look up the transaction type and flip the sign if it is a credit
        transaction.

    """

    def __init__(self, *args, **kwargs):
        # based on - https://stackoverflow.com/a/60118733
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for field in self.fields:
                if isinstance(self.fields[field], forms.DecimalField):
                    if self.instance.type in self._meta.model.negatives:
                        tmp = self.initial[field]
                        self.initial[field] = -1 * tmp


class SalesAndPurchaseTransactionSearchForm(forms.Form):

    contact = forms.CharField(
        label='',
        max_length=100,
        required=False
    )
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
    search_within = forms.ChoiceField(
        choices=(
            ('any', 'Any'),
            ('tran', 'Transaction date'),
            ('due', 'Due Date')
        )
    )
    start_date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
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
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        ),
        required=False
    )
    include_voided = forms.BooleanField(
        label="Include Voided Transactions", initial=False)
    # used in BaseTransactionList view
    use_adv_search = forms.BooleanField(initial=False)
    # w/o this adv search is not applied

    def __init__(self, *args, **kwargs):
        contact_name = kwargs.pop("contact_name", "contact")
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.form_tag = False
        self.helper.form_show_errors = False
        self.helper.include_media = False

        self.fields["contact"].label = contact_name.capitalize()

        self.helper.layout = Layout(
            Div(
                Div(
                    Div(
                        AdvSearchField(
                            'contact',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'reference',
                            css_class="w-100 input",
                        ),
                        css_class="col-5"
                    ),
                    Div(
                        AdvSearchField(
                            'total',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                Div(
                    Div(
                        AdvSearchField(
                            'period',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'search_within',
                            css_class="w-100",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'start_date',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'end_date',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                Field('use_adv_search', type="hidden"),
                AdvSearchField('include_voided'),
            ),
            HTML(
                '<div class="d-flex align-items-center justify-content-end my-4">'
                '<button class="btn button-secondary search-btn">Search</button>'
                '<span class="small ml-2 clear-btn">or <a href="#">Clear</a></span>'
                '</div>'
            ),
        )

    def clean_start_date(self):
        start_date = self.cleaned_data["start_date"]
        return start_date


class NominalTransactionSearchForm(forms.Form):

    nominal = forms.CharField(
        label='Nominal',
        max_length=100,
        required=False
    )
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
    date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        ),
        required=False
    )
    include_voided = forms.BooleanField(label="Include Voided Transactions")
    use_adv_search = forms.BooleanField()  # used in BaseTransactionList view
    # w/o this adv search is not applied

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.form_tag = False
        self.helper.form_show_errors = False
        self.helper.include_media = False  # I decide where the js goes
        self.helper.layout = Layout(
            Div(
                Div(
                    Div(
                        AdvSearchField(
                            'nominal',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'reference',
                            css_class="w-100 input",
                        ),
                        css_class="col-5"
                    ),
                    Div(
                        AdvSearchField(
                            'total',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                Div(
                    Div(
                        AdvSearchField(
                            'period',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'date',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                AdvSearchField('include_voided'),
                Field('use_adv_search', type="hidden"),
            ),
            HTML(
                '<div class="d-flex align-items-center justify-content-end my-4">'
                '<button class="btn button-secondary search-btn">Search</button>'
                '<span class="small ml-2 clear-btn">or <a href="#">Clear</a></span>'
                '</div>'
            ),
        )

    def clean_date(self):
        date = self.cleaned_data["date"]
        return date


class CashBookTransactionSearchForm(forms.Form):

    cash_book = forms.CharField(
        label='Cash Book',
        max_length=100,
        required=False
    )
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
    date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
            },
            attrs={
                "icon_toggle": True,
                "input_group": False
            }
        ),
        required=False
    )
    include_voided = forms.BooleanField(label="Include Voided Transactions")
    use_adv_search = forms.BooleanField()  # used in BaseTransactionList view
    # w/o this adv search is not applied

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "GET"
        self.helper.form_tag = False
        self.helper.form_show_errors = False
        self.helper.include_media = False  # I decide where the js goes
        self.helper.layout = Layout(
            Div(
                Div(
                    Div(
                        AdvSearchField(
                            'cash_book',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'reference',
                            css_class="w-100 input",
                        ),
                        css_class="col-5"
                    ),
                    Div(
                        AdvSearchField(
                            'total',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                Div(
                    Div(
                        AdvSearchField(
                            'period',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    Div(
                        AdvSearchField(
                            'date',
                            css_class="w-100 input",
                        ),
                        css_class="col-2"
                    ),
                    css_class="row"
                ),
                AdvSearchField('include_voided'),
                Field('use_adv_search', type="hidden"),
            ),
            HTML(
                '<div class="d-flex align-items-center justify-content-end my-4">'
                '<button class="btn button-secondary search-btn">Search</button>'
                '<span class="small ml-2 clear-btn">or <a href="#">Clear</a></span>'
                '</div>'
            ),
        )

    def clean_date(self):
        date = self.cleaned_data["date"]
        return date


class BaseTransactionHeaderForm(BaseTransactionMixin, forms.ModelForm):

    date = forms.DateField(
        widget=DatePicker(
            options={
                "useCurrent": True,
                "collapse": True,
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
            self.fields["type"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        type = cleaned_data.get("type")
        total = cleaned_data.get("total")
        if type in self._meta.model.negatives:
            cleaned_data["total"] = -1 * total
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.due = instance.total - instance.paid
        if commit:
            instance.save()
        return instance


class SaleAndPurchaseHeaderFormMixin:
    def __init__(self, *args, **kwargs):
        contact_model_name = kwargs.pop("contact_model_name")
        super().__init__(*args, **kwargs)
        # it might be tempting to change the url the form is posted to on the client
        # to include the GET parameter but this means adding a further script to
        # the edit view on the clientside because we do not reload the edit view on changing
        # the type
        if self.data:
            _type = self.data.get(self.prefix + "-" + "type")
        else:
            _type = self.initial.get('type')

        if _type in self._meta.model.payment_type:
            if _type in self._meta.model.get_types_requiring_analysis():
                payment_form = True
                payment_brought_forward_form = False
                self.fields["cash_book"].required = True
            else:
                payment_form = True
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


class ReadOnlyBaseTransactionHeaderForm(BaseTransactionHeaderForm):
    """
    Remove the datepicker widget since it is not needed in read only view.
    """
    date = forms.DateField()
    due_date = forms.DateField()


class ReadOnlySaleAndPurchaseHeaderFormMixin:
    def __init__(self, *args, **kwargs):
        contact_model_name = kwargs.get("contact_model_name")
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.fields["type"].widget = forms.TextInput(
            attrs={"class": "w-100 input"})

        self.fields[contact_model_name].widget = forms.TextInput()
        contact_queryset = self.fields[contact_model_name].queryset

        self.initial[contact_model_name] = str(
            contact_queryset[0]
        )
        _type = self.initial["type"]

        if _type in self._meta.model.payment_type:
            if _type in self._meta.model.get_types_requiring_analysis():
                payment_form = True
                payment_brought_forward_form = False
                self.fields["cash_book"].widget = forms.TextInput()
                cash_book = self.fields["cash_book"].queryset[0]
                self.initial["cash_book"] = str(cash_book)
            else:
                payment_form = False
                payment_brought_forward_form = True
        else:
            payment_brought_forward_form = False
            payment_form = False

        self.helper = create_transaction_header_helper(
            {
                'contact': contact_model_name,
            },
            payment_form=payment_form,
            payment_brought_forward_form=payment_brought_forward_form,
            read_only=True
        )
        # must do this afterwards
        self.initial["type"] = self.instance.get_type_display()


class BaseTransactionModelFormSet(forms.BaseModelFormSet):

    def get_ordering_widget(self):
        return forms.HiddenInput(attrs={'class': 'ordering'})


class BaseTransactionLineForm(forms.ModelForm):

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


class BaseLineFormset(BaseTransactionModelFormSet):

    def __init__(self, *args, **kwargs):
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
        header_type_is_negative = self.header.is_negative_type()
        multiplier = -1 if header_type_is_negative else 1
        for form in self.forms:
            # empty_permitted = False is set on forms for existing data
            # empty_permitted = True is set new forms i.e. for non existent data
            if not form.empty_permitted or (form.empty_permitted and form.has_changed()):
                if not form.cleaned_data.get("DELETE"):
                    form.instance.goods *= multiplier
                    form.instance.vat *= multiplier
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


line_css_classes = {
    "Td": {
        "item": "h-100 w-100 border-0",
        "description": "can_highlight h-100 w-100 border-0",
        "nominal": "h-100 w-100 border-0",
        "goods": "can_highlight h-100 w-100 border-0",
        "vat_code": "h-100 w-100 border-0",
        "vat": "can_highlight w-100 h-100 border-0"
    }
}


class BroughtForwardLineForm(BaseTransactionLineForm, BaseAjaxForm):

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

        if self.instance.pk:
            for field in self.fields:
                if isinstance(self.fields[field], forms.DecimalField):
                    if self.header.is_negative_type():
                        tmp = self.initial[field]
                        self.initial[field] = -1 * tmp

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
            field_layout_overrides={
                'Td': {
                    'item': PlainFieldErrors,
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                }
            }
        ).render()


class ReadOnlySaleAndPurchaseLineFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True
        self.helpers = TableHelper(
            self._meta.fields,
            order=False,
            delete=False,
            css_classes={
                "Td": {
                    "item": "input-disabled text-left",
                    "description": "input-disabled text-left",
                    "nominal": "input-disabled text-left",
                    "goods": "input-disabled text-left",
                    "vat_code": "input-disabled text-left",
                    "vat": "input-disabled text-left"
                }
            },
            field_layout_overrides={
                'Td': {
                    'item': PlainFieldErrors,
                    'description': PlainFieldErrors,
                    'nominal': PlainFieldErrors,
                    'amount': PlainFieldErrors
                }
            },
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
    is done in clean.

    """

    # readonly not permitted for select element so disable used and on client we enable the element before the form is submitted
    # search 'CLIENT JS ITEM 1'.  Currently in edit_matching_js.html
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

        # # Setting the disabled attribute means even if the user tampers
        # # with the html widget django discounts the change
        # for field in self.fields:
        #     if field != "value":
        #         self.fields[field].disabled = True

        # GET request for CREATE
        if not self.data and not self.instance.pk:
            q = self.fields["matched_to"].queryset
            self.fields["matched_to"].queryset = q.none()
        # GET and POST requests for CREATE AND EDIT
        if self.instance.pk:
            if self.tran_being_created_or_edited.pk == self.instance.matched_to_id:
                matched_header = self.instance.matched_by
                f = -1
            else:
                matched_header = self.instance.matched_to
                f = 1
            self.fields["type"].initial = matched_header.type
            self.fields["ref"].initial = matched_header.ref
            self.fields["total"].initial = matched_header.total
            self.fields["paid"].initial = matched_header.paid
            self.fields["due"].initial = matched_header.due
            self.initial["value"] *= f
            # matched_to is a field rendered on the client because it is for the user to pick (in some situations)
            # but matched_by, although a field, can always be determined server side so we override the POST data to do so
            if self.tran_being_created_or_edited.pk:
                self.data = self.data.copy()
                # we are editing a transaction in the system
                self.data[self.prefix + "-" +
                          "matched_by"] = self.initial.get('matched_by', self.tran_being_created_or_edited.pk)
                # FIX ME - set matched_by to read only so we don't need to do this
        if not self.instance.pk and self.data:
            # creating a new transaction
            # matched_by is not required at form level therefore
            # view will attach matched_by to instance after successful validation
            self.fields["matched_by"].required = False

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
        # The purpose of this clean is to check that each match is valid
        # But we can only do the check if the matched_to transaction in the relationship IS NOT the
        # transaction being created or edited.  Well, the transaction must be being edited if
        # it is a matched to.
        # This is because we don't know how much is being matched to other transactions at this point
        cleaned_data = super().clean()
        initial_value = self.initial.get("value", 0)
        matched_by = cleaned_data.get("matched_by")
        matched_to = cleaned_data.get("matched_to")
        value = cleaned_data.get("value")
        header = matched_to
        # check transaction exists as attribute first because it will not if the header_form fails
        if hasattr(self, 'tran_being_created_or_edited'):
            if self.tran_being_created_or_edited.pk:
                # so tran is being edited not created
                if self.tran_being_created_or_edited.pk == matched_to.pk:
                    header = matched_by
                    # We still need to check the value is acceptable
        else:
            return  # header_form must have failed so do not bother checking anything further
        # The header then at this point is NOT the transaction being created or edited.  Since only one matching record
        # can map any two transactions we can with certainly determine whether the value to match is valid or not.
        # To be clear - header here is NOT the transaction created / edited by the header form.
        # header.due is therefore fixed.
        if header and value:
            if header.total > 0:
                if value < 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
                elif value > header.due + initial_value:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
            elif header.total < 0:
                if value > 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )
                elif value < header.due + initial_value:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"Value must be between 0 and {header.due + initial_value}"
                            ),
                            code="invalid-match"
                        )
                    )

            would_be_due = header.due + (initial_value - value)
            if header.total > 0:
                if would_be_due < 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"This isn't possible because of the matching transaction"
                            )
                        )
                    )
                elif would_be_due > header.total:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"This isn't possible because of the matching transaction"
                            )
                        )
                    )
            elif header.total < 0:
                if would_be_due > 0:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"This isn't possible because of the matching transaction"
                            )
                        )
                    )
                if would_be_due < header.total:
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _(
                                f"This isn't possible because of the matching transaction"
                            )
                        )
                    )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.matched_to_id != self.tran_being_created_or_edited.pk:
            instance.matched_by = self.tran_being_created_or_edited
        if commit:
            instance.save()
        return instance


class ReadOnlySaleAndPurchaseMatchingFormMixin:

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].disabled = True

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
                    "value": "input-disabled"
                }
            },
            field_layout_overrides={
                'Td': {
                    'type': DataTableTdField,
                    'ref': DataTableTdField,
                    'total': DataTableTdField,
                    'paid': DataTableTdField,
                    'due': DataTableTdField,
                    'value': DataTableTdField,
                }
            }
        ).render()


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

    def clean(self):
        super().clean()
        if(any(self.errors) or not hasattr(self, 'tran_being_created_or_edited')):
            return
        # undo the effects of matching to date
        self.tran_being_created_or_edited.due = self.tran_being_created_or_edited.total
        self.tran_being_created_or_edited.paid = 0
        total_matching_value = 0
        self.headers = []
        header_to_update = None
        for form in self.forms:
            initial_value = form.initial.get("value", 0)
            value = form.instance.value
            diff = value - initial_value
            total_matching_value += value
            if not form.instance.matched_by_id or self.tran_being_created_or_edited.pk == form.instance.matched_by_id:
                # either new transaction is being created
                # or we are editing a transaction.
                # here we just consider those matches where matched_by is the transaction being edited.
                header_to_update = form.instance.matched_to
            else:
                # FIX LATER ON.  ONE TEST AT LEAST WILL FAIL WITH THIS
                form.instance.value = -1 * value
                header_to_update = form.instance.matched_by
            header_to_update.due -= diff
            header_to_update.paid += diff
            self.headers.append(header_to_update)
        if self.tran_being_created_or_edited.total == 0:
            if total_matching_value != 0:
                raise forms.ValidationError(
                    _(
                        f"You are trying to match a total value of { total_matching_value }.  "
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
                self.tran_being_created_or_edited.due += total_matching_value
                if self.tran_being_created_or_edited.due >= 0 and self.tran_being_created_or_edited.due <= self.tran_being_created_or_edited.total:
                    self.tran_being_created_or_edited.paid += (-1 *
                                                               total_matching_value)
                else:
                    raise forms.ValidationError(
                        _(
                            f"Please ensure the total of the transactions you are matching is between 0 and { -1 * self.tran_being_created_or_edited.total }"
                        ),
                        code="invalid-match"
                    )
        elif self.tran_being_created_or_edited.total < 0:
            if self.forms:
                self.tran_being_created_or_edited.due += total_matching_value
                if self.tran_being_created_or_edited.due <= 0 and self.tran_being_created_or_edited.due >= self.tran_being_created_or_edited.total:
                    self.tran_being_created_or_edited.paid += (-1 *
                                                               total_matching_value)
                else:
                    raise forms.ValidationError(
                        _(
                            f"Please ensure the total of the transactions you are matching is between 0 and { -1 * self.tran_being_created_or_edited.total }"
                        )
                    )


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
            self.instance = self.header_model.objects.exclude(status="v").get(
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
                            "period", css_class="input w-100"),
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
                    css_class="mt-4 row"
                ),
                Div(
                    HTML("<button class='btn btn-sm btn-primary'>Report</button>"),
                    css_class="text-right mt-3"
                )
            )

    return Form

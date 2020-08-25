from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout
from django import forms
from django.utils.translation import ugettext_lazy as _
from tempus_dominus.widgets import DatePicker

# do we need to import Hidden ??


class Delete(Div):
    template = "accounts/layout/delete.html"


class Draggable(Div):
    template = "accounts/layout/draggable.html"


class Label(Field):
    template = "accounts/layout/label_only.html"


class PlainField(Field):
    # no label or errors; field only
    template = "accounts/layout/plain_field.html"


class PlainFieldErrors(Field):
    # no label; field and errors only
    template = "accounts/layout/plain_field_errors.html"


class DataTableTdField(Field):
    # native sorting in jquery datatables is possible by including the field value in a <span> element
    # this is necessary for those td elements which contain <input elements>
    template = "accounts/layout/data_table_td_field.html"


class Td(Div):
    template = "accounts/layout/td.html"


class Th(Div):
    template = "accounts/layout/th.html"


class Tr(Div):
    template = "accounts/layout/tr.html"


class LabelAndFieldOnly(Field):
    template = "accounts/layout/label_and_field.html"


class LabelAndFieldAndErrors(Field):
    template = "accounts/layout/label_and_field_and_error.html"


class AdvSearchField(Field):
    template = "accounts/layout/adv_search_field.html"


class AjaxForm(forms.ModelForm):
    """

    Forms which use fields which have widgets which are populated
    clientside via AJAX need to have different querysets depending
    on whether data is being posted, or the form is being rendered
    clientside, or the the form is being used to edit data.

    This class assumes the subclass defines the ajax_fields on
    the Meta propety.

    With models the Meta class seems to lose any customised
    attributes but with forms this DOES seem to work.

    THIS FORM ONLY MAKES SENSE TO USE WITH THE AJAXMODELCHOICE
    FIELD I CREATED, OR ANOTHER FIELD WHICH CAN TAKE THE
    SAME ATTRIBUTES.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            # querysets if data is being posted
            self.set_querysets("post_queryset")
        elif self.instance.pk:
            # querysets if form is for an instance
            self.set_querysets("inst_queryset")
        else:
            # querysets for brand new form
            self.set_querysets("get_queryset")

    def set_querysets(self, queryset_attr):
        for field in self.Meta.ajax_fields:
            queryset = getattr(self.fields[field], queryset_attr)
            if queryset_attr == "inst_queryset":
                queryset = queryset(self.instance)
            self.fields[field].queryset = queryset


class TableHelper(object):

    def __init__(self, fields, order=False, delete=False, **kwargs):
        self.fields = fields
        self.order = order
        self.delete = delete
        self.css_classes = kwargs.get("css_classes", {})
        self.field_layout_overrides = kwargs.get("field_layout_overrides", {})
        self.column_layout_object_css_classes = kwargs.get(
            "column_layout_object_css_classes", {})
        # example {"Td": {"type": LabelAndField}}
        # must use Td namespace

    def create_field_columns(self, fields, column_layout_object, field_layout_object, _type):
        css_classes = self.css_classes.get(_type, {})
        field_overrides = self.field_layout_overrides.get(_type, {})
        column_layout_object_css_classes = self.column_layout_object_css_classes.get(
            _type, {})
        return [
            column_layout_object(
                field_overrides.get(field, field_layout_object)(
                    field,
                    css_class=css_classes.get(field, '')
                ),
                css_class="col-" + field +
                (" d-none" if field == "id" else "") + " " +
                column_layout_object_css_classes.get(field, '')
            )
            for field in fields
        ]

    def create_thead_or_tbody(self, column_layout_object, field_layout_object,
                              drag_layout_object, delete_layout_object, _type):
        field_columns = []
        if self.order:
            order_args = [drag_layout_object]
            if _type == "Td":
                order_args += [PlainField('ORDER',
                                          type="hidden", css_class="ordering")]
            field_columns += [
                column_layout_object(
                    *order_args,
                    css_class="pointer col-draggable-icon"
                )
            ]
        field_columns += self.create_field_columns(
            self.fields, column_layout_object, field_layout_object, _type)
        if self.delete:
            delete_args = [delete_layout_object]
            if _type == "Td":
                delete_args += [PlainField('DELETE', css_class="delete-line d-none")]
            field_columns += [
                column_layout_object(
                    *delete_args,
                    # FIX ME - change this from col-draggable-icon to col-deletable-icon
                    css_class="pointer col-close-icon"
                )
            ]
        return field_columns

    def create_transaction_table_formset_helper(self, field_columns, tr_class=""):
        class TransactionHelper(FormHelper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.form_tag = False
                self.disable_csrf = True
                self.layout = Layout(
                    Tr(
                        *field_columns,
                        css_class=tr_class
                    )
                )
        return TransactionHelper()

    def create_thead(self, tr_class=""):
        field_columns = self.create_thead_or_tbody(
            Th, Label, HTML(''), HTML(''), "Th")
        return self.create_transaction_table_formset_helper(field_columns, tr_class)

    def create_tbody(self, tr_class=""):
        field_columns = self.create_thead_or_tbody(
            Td,
            PlainField,
            Draggable(),
            Delete(),
            "Td"
        )
        return self.create_transaction_table_formset_helper(field_columns, tr_class)

    def render(self):
        return {
            "thead": self.create_thead(),
            "tbody": self.create_tbody(),
            "empty_form": self.create_tbody("d-none empty-form")
        }






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
                    if self.instance.type in self._meta.model.credits:
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
    include_voided = forms.BooleanField(label="Include Voided Transactions", initial=False)
    use_adv_search = forms.BooleanField(initial=False) # used in BaseTransactionList view
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
    use_adv_search = forms.BooleanField() # used in BaseTransactionList view
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


    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.due = instance.total - instance.paid
        if commit:
            instance.save()
        return instance


class ReadOnlyBaseTransactionHeaderForm(BaseTransactionHeaderForm):
    """
    Remove the datepicker widget since it is not needed in read only view.
    """
    date = forms.DateField()
    due_date = forms.DateField()


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
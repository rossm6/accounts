from crispy_forms.layout import (HTML, Div, Field, Hidden, Layout,)
from crispy_forms.helper import FormHelper
from django import forms

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

class Td(Div):
    template = "accounts/layout/td.html"

class Th(Div):
    template = "accounts/layout/th.html"

class Tr(Div):
    template = "accounts/layout/tr.html"

class LabelAndFieldOnly(Field):
    template = "accounts/layout/label_and_field.html"
    # fix me - better name the HTML file

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
    FIELD I CREATED.  OR ANOTHER FIELD WHICH CAN TAKE THE
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



def create_transaction_header_helper(generic_to_fields_map):

    """
    This will returns the standard header help for transaction forms
    """

    class StandardHeaderHelper(FormHelper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.form_tag = False
            self.disable_csrf = True
            self.form_show_errors = False
            self.include_media = False
            self.layout = Layout(
                Div(
                    Div(
                        PlainField(generic_to_fields_map.get("type", "type"), css_class="transaction-type-select"),
                        css_class="form-group mr-2"
                    ),
                    Div(
                        Div(
                            Div(
                                LabelAndFieldOnly(generic_to_fields_map.get("contact", "contact"), css_class="supplier-select"), # FIX ME - change to contact-select
                                css_class="form-group mr-2"
                            ),
                            Div(
                                LabelAndFieldOnly(generic_to_fields_map.get("ref", "ref"), css_class="w-100 input"),
                                css_class="form-group mr-2"
                            ),
                            Div(
                                LabelAndFieldOnly(generic_to_fields_map.get("date", "date"), css_class="w-100 input"),
                                css_class="form-group mr-2 position-relative"
                            ),
                            Div(
                                LabelAndFieldOnly(generic_to_fields_map.get("due_date", "due_date"), css_class="w-100 input"),
                                css_class="form-group mr-2 position-relative"
                            ),
                            css_class="d-flex justify-content-between" 
                        ),
                        Div(
                            LabelAndFieldOnly(generic_to_fields_map.get("total", "total"), css_class="w-100 input"),
                            css_class="form-group"
                        ),
                        css_class="mb-4 d-flex justify-content-between"
                    ),
                )
            )
    
    return StandardHeaderHelper()




def create_transaction_table_formset_helper(field_columns, tr_class=""):
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


def create_field_columns(fields, column_layout_object, field_layout_object, css_classes={}):
    return [ 
        column_layout_object(
            field_layout_object(
                field,
                css_class=css_classes.get(field, "")
            ), 
            css_class="col-" + field
        ) 
        for field in fields 
    ]


def create_thead_helper(fields, tr_class="", css_classes={}):
    field_columns = [ 
        Th(
            HTML(''), css_class="pointer col-draggable-icon"
        ) 
    ]
    field_columns += create_field_columns(fields, Th, Label, css_classes) # Th class defined above
    field_columns += [
        Th(
            HTML(''),
            css_class="pointer col-draggable-icon" # FIX ME - change this from col-draggable-icon to col-deletable-icon
        )
    ]
    return create_transaction_table_formset_helper(field_columns, tr_class)


def create_tbody_helper(fields, tr_class="", css_classes={}):
    field_columns = [ 
        Td(
            Draggable(),
            css_class="pointer col-draggable-icon"
        ),
    ]
    field_columns += create_field_columns(fields, Td, PlainField, css_classes) # Th class defined above
    field_columns += [
        Td(
            Delete(),
            PlainField('ORDER', type="hidden", css_class="ordering"),
            css_class="pointer col-close-icon"
        )
    ]
    return create_transaction_table_formset_helper(field_columns, tr_class)



class TableHelper(object):

    def __init__(self, fields, order=False, delete=False, **kwargs):
        self.fields = fields
        self.order=order
        self.delete=delete
        self.css_classes = kwargs.get("css_classes", {})
        self.field_layout_overrides = kwargs.get("field_layout_overrides", {})
        # example {"Td": {"type": LabelAndField}}
        # must use Td namespace

    def create_field_columns(self, fields, column_layout_object, field_layout_object, _type):
        css_classes = self.css_classes.get(_type, {})
        field_overrides = self.field_layout_overrides.get(_type, {})
        return [ 
            column_layout_object(
                field_overrides.get(field, field_layout_object)(
                    field,
                    css_class=css_classes.get(field, '')
                ),
                css_class="col-" + field
            ) 
            for field in fields 
        ]

    def create_thead_or_tbody(self, column_layout_object, field_layout_object, 
                    drag_layout_object, delete_layout_object, _type):
        field_columns = []
        if self.order:
            order_args = [ drag_layout_object ]
            if _type == "Td":
                order_args += [ PlainField('ORDER', type="hidden", css_class="ordering") ]
            field_columns += [
                column_layout_object(
                    *order_args,
                    css_class="pointer col-draggable-icon"
                ) 
            ]
        field_columns += self.create_field_columns(self.fields, column_layout_object, field_layout_object, _type)
        if self.delete:
            field_columns += [
                column_layout_object(
                    delete_layout_object,
                    css_class="pointer col-close-icon" # FIX ME - change this from col-draggable-icon to col-deletable-icon
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
        field_columns = self.create_thead_or_tbody(Th, Label, HTML(''), HTML(''), "Th")
        return self.create_transaction_table_formset_helper(field_columns, tr_class)

    def create_tbody(self, tr_class=""):
        field_columns = self.create_thead_or_tbody(Td, PlainField, Draggable(), Delete(), "Td")
        return self.create_transaction_table_formset_helper(field_columns, tr_class)

    def render(self):
        return {
            "thead": self.create_thead(),
            "tbody": self.create_tbody(),
            "empty_form": self.create_tbody("d-none empty-form")
        }
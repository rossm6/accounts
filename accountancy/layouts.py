from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout

# do we need to import Hidden ??


class AdjustPeriod(Div):
    """
    Used for adjusting FYs
    """
    template = "accounts/layout/fy_adjust.html"


class PeriodInputGroup(Div):
    template = "accounts/layout/period_input_group.html"


class FYInputGroup(Div):
    template = "accounts/layout/fy_input_group.html"


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
    # but errors are kind used in grid where it just highlights the corner of the input
    template = "accounts/layout/plain_field_errors.html"


class FieldAndErrors(Field):
    template = "accounts/layout/field_and_errors_list.html"


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


def create_transaction_enquiry_time_fields(search_within=False):
    row = [
        Div(
            LabelAndFieldAndErrors(
                'period',
                css_class="w-100 form-control form-control-sm",
            ),
            css_class="col-2"
        )
    ]
    if search_within:
        row += [
            Div(
                LabelAndFieldAndErrors(
                    'search_within', css_class="form-control form-control-sm"),
                css_class="col-2"
            )
        ]
    row += [
        Div(
            LabelAndFieldAndErrors(
                'start_date',
                css_class="w-100 form-control form-control-sm",
            ),
            css_class="col-2"
        ),
        Div(
            LabelAndFieldAndErrors(
                'end_date',
                css_class="w-100 form-control form-control-sm",
            ),
            css_class="col-2"
        )
    ]
    return row


def create_transaction_enquiry_layout(main_choice, include_voided=False, include_brought_forwards=False, search_within=False):
    second_row = create_transaction_enquiry_time_fields(
        search_within=search_within)
    third_row = []
    if include_voided:
        third_row.append(
            LabelAndFieldAndErrors('include_voided')
        )
    if include_brought_forwards:
        third_row.append(
            LabelAndFieldAndErrors('include_brought_forwards')
        )

    return Layout(
        Div(
            Div(
                Div(
                    LabelAndFieldAndErrors(
                        main_choice,
                        css_class="form-control form-control-sm"
                    ),
                    css_class="col"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'reference',
                        css_class="w-100 form-control form-control-sm",
                    ),
                    css_class="col-5"
                ),
                Div(
                    LabelAndFieldAndErrors(
                        'total',
                        css_class="w-100 form-control form-control-sm",
                    ),
                    css_class="col-2"
                ),
                css_class="row"
            ),
            Div(
                *second_row,
                css_class="row mt-3"
            ),
            Field('use_adv_search', type="hidden"),
            Div(
                *third_row,
                css_class="mt-3"
            )
        ),
    )


def create_transaction_header_helper(generic_to_fields_map, payment_form=False, payment_brought_forward_form=False, read_only=False):
    """

    This will returns the standard header help for transaction forms

    The only difference with the header form for a payment or refund is we don't need
    the due date field.  Because we are using the same form either way we need to hide
    this field.  If later the decision is made to use a different form remember that
    the edit form needs the ability to change transaction on the client side....

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
                        # this field does not show errrors but there shouldn't ever be any errors for this field
                        PlainField(generic_to_fields_map.get("type", "type"), css_class=(
                            "input input-disabled text-left border" if read_only else "form-control form-control-sm transaction-type-select")),
                        css_class="form-group mr-2"
                    ),
                    (
                        Div(
                            LabelAndFieldAndErrors('cash_book', css_class=(
                                "input input-disabled text-left border" if read_only else "cashbook-select form-control form-control-sm")),
                            css_class="form-group mr-2"
                        )
                        if payment_form and not payment_brought_forward_form
                        else
                        HTML('')
                    ),
                    Div(
                        Div(
                            Div(
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get("contact", "contact"), css_class=(
                                        "input input-disabled text-left border" if read_only else "contact-select form-control form-control-sm")),
                                    css_class="col-2"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "ref", "ref"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                    css_class="col-2"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "period", "period"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                    css_class="col-2 position-relative"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "date", "date"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                    css_class="col-2 position-relative"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "due_date", "due_date"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                    css_class="col-2 position-relative" + \
                                    (" d-none" if (payment_form or payment_brought_forward_form) else "")
                                ),
                                css_class="row"
                            ),
                            css_class="col-10"
                        ),
                        Div(
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "total", "total"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="form-group"
                            ),
                            css_class="col-2"
                        ),
                        css_class="mb-4 row"
                    ),
                )
            )

    return StandardHeaderHelper()


def create_journal_header_helper(generic_to_fields_map={}, read_only=False):
    """

    This will returns the standard header help for transaction forms

    The only difference with the header form for a payment or refund is we don't need
    the due date field.  Because we are using the same form either way we need to hide
    this field.  If later the decision is made to use a different form remember that
    the edit form needs the ability to change transaction on the client side....

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
                        # this field does not show errrors but there shouldn't ever be any errors for this field
                        PlainField(generic_to_fields_map.get("type", "type"), css_class=(
                            "input input-disabled text-left border" if read_only else "transaction-type-select form-control form-control-sm")),
                        css_class="form-group mr-2"
                    ),
                    Div(
                        Div(
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "ref", "ref"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col mr-2"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "period", "period"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col position-relative"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "date", "date"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col position-relative"
                            ),
                            Div(
                                LabelAndFieldAndErrors(
                                    "vat_type", css_class="vat_type_selectize form-control form-control-sm"),
                                css_class="col position-relative"
                            ),
                            css_class="form-row"
                        ),
                        Div(
                            LabelAndFieldAndErrors(generic_to_fields_map.get(
                                "total", "total"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                            css_class="form-group"
                        ),
                        css_class="mb-4 d-flex justify-content-between"
                    )
                )
            )

    return StandardHeaderHelper()


def create_cashbook_header_helper(generic_to_fields_map={}, read_only=False):
    """

    This will returns the standard header help for transaction forms

    The only difference with the header form for a payment or refund is we don't need
    the due date field.  Because we are using the same form either way we need to hide
    this field.  If later the decision is made to use a different form remember that
    the edit form needs the ability to change transaction on the client side....

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
                        # this field does not show errrors but there shouldn't ever be any errors for this field
                        PlainField(generic_to_fields_map.get("type", "type"), css_class=(
                            "input input-disabled text-left border" if read_only else "transaction-type-select form-control form-control-sm")),
                        css_class="form-group mr-2"
                    ),
                    Div(
                        # this field does not show errrors but there shouldn't ever be any errors for this field
                        PlainField(generic_to_fields_map.get("cash_book", "cash_book"), css_class=(
                            "input input-disabled text-left border" if read_only else "cashbook-select form-control form-control-sm")),
                        css_class="form-group mr-2"
                    ),
                    Div(
                        Div(
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "ref", "ref"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col mr-2"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "period", "period"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col position-relative"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "date", "date"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                                css_class="col position-relative"
                            ),
                            Div(
                                LabelAndFieldAndErrors(
                                    "vat_type", css_class="vat_type_selectize form-control form-control-sm"),
                                css_class="col-3 position-relative"
                            ),
                            css_class="form-row"
                        ),
                        Div(
                            LabelAndFieldAndErrors(generic_to_fields_map.get(
                                "total", "total"), css_class="input input-disabled text-left border" if read_only else "w-100 form-control form-control-sm"),
                            css_class="form-group"
                        ),
                        css_class="mb-4 d-flex justify-content-between"
                    ),
                )
            )

    return StandardHeaderHelper()


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
                delete_args += [PlainField('DELETE',
                                           css_class="delete-line d-none")]
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
            PlainFieldErrors,
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

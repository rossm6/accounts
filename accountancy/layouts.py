from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout

from accountancy.forms import PlainField, LabelAndFieldAndErrors


def create_transaction_header_helper(generic_to_fields_map, payment_form=False, read_only=False):
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
                            "input input-disabled text-left border" if read_only else "transaction-type-select")),
                        css_class="form-group mr-2"
                    ),
                    (
                        Div(
                            LabelAndFieldAndErrors('cash_book', css_class=(
                                "input input-disabled text-left border" if read_only else "cashbook-select")),
                            css_class="form-group mr-2"
                        )
                        if payment_form
                        else
                        HTML('')
                    ),
                    Div(
                        Div(
                            Div(
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get("contact", "contact"), css_class=(
                                        "input input-disabled text-left border" if read_only else "supplier-select w-100")),  # FIX ME - change to contact-select
                                    css_class="col-2"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "ref", "ref"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                    css_class="col-2"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "period", "period"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                    css_class="col-2 position-relative"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "date", "date"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                    css_class="col-2 position-relative"
                                ),
                                Div(
                                    LabelAndFieldAndErrors(generic_to_fields_map.get(
                                        "due_date", "due_date"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                    css_class="col-2 position-relative" + \
                                    (" d-none" if payment_form else "")
                                ),
                                css_class="row"
                            ),
                            css_class="col-10"
                        ),
                        Div(
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "total", "total"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
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
                            "input input-disabled text-left border" if read_only else "transaction-type-select")),
                        css_class="form-group mr-2"
                    ),
                    Div(
                        Div(
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "ref", "ref"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                css_class="form-group mr-2"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "period", "period"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                css_class="form-group mr-2 position-relative"
                            ),
                            Div(
                                LabelAndFieldAndErrors(generic_to_fields_map.get(
                                    "date", "date"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                                css_class="form-group mr-2 position-relative"
                            ),
                            css_class="d-flex justify-content-between"
                        ),
                        Div(
                            LabelAndFieldAndErrors(generic_to_fields_map.get(
                                "total", "total"), css_class="input input-disabled text-left border" if read_only else "w-100 input"),
                            css_class="form-group"
                        ),
                        css_class="mb-4 d-flex justify-content-between"
                    ),
                )
            )

    return StandardHeaderHelper()

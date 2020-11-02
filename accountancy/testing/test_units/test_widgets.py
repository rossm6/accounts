import mock
from accountancy.fields import ModelChoiceIteratorWithFields
from accountancy.widgets import SelectWithDataAttr
from django.forms.models import ModelChoiceIterator
from django.test import TestCase
from vat.models import Vat


class SelectWithDataAttrTests(TestCase):
    """
    This widget is an extension of Select.  It only adds data attributes to the
    option and the select elements.
    """

    def test_normal_select_widget_without_groups(self):
        """
        Using it like a select widget
        """
        vat = Vat.objects.create(code="1", name="standard", rate="20")
        mock_field = mock.Mock()
        mock_field.empty_label = ""
        mock_field.label_from_instance = lambda o: str(o)
        mock_field.prepare_value = lambda o: o.pk
        mock_field.queryset = Vat.objects.all()
        it = ModelChoiceIterator(mock_field)
        it = iter(it)
        widget = SelectWithDataAttr(choices=it)
        # ctx = widget.get_context("vat", vat.pk, {})
        widget_html = widget.render("vat", vat.pk)
        self.assertHTMLEqual(
            widget_html,
            f"""<select name="vat">
                <option value=""></option>

                <option value="{vat.pk}" selected>1 - standard - 20.00%</option>

            </select>"""
        )

    def test_with_data_option_attrs_without_model_attrs(self):
        """
        Check that data-option-attrs works without model attrs.
        This is pointless but need to check it doesn't break the widget.
        """
        vat = Vat.objects.create(code="1", name="standard", rate="20")
        mock_field = mock.Mock()
        mock_field.empty_label = ""
        mock_field.label_from_instance = lambda o: str(o)
        mock_field.prepare_value = lambda o: o.pk
        mock_field.queryset = Vat.objects.all()
        it = ModelChoiceIterator(mock_field)
        it = iter(it)
        widget = SelectWithDataAttr(choices=it, attrs={"data-option-attrs": ["rate"]})
        # ctx = widget.get_context("vat", vat.pk, {})
        widget_html = widget.render("vat", vat.pk)
        self.assertHTMLEqual(
            widget_html,
            f"""<select name="vat">
            <option value=""></option>

            <option value="{vat.pk}" selected>1 - standard - 20.00%</option>

            </select>"""
        )

    def test_with_data_option_attrs_with_model_attrs(self):
        """
        Using the widget now for what is was created for.

        We need to use a different model iterator so that the extra
        fields are passed to the widget.
        """
        vat = Vat.objects.create(code="1", name="standard", rate="20")
        mock_field = mock.Mock()
        mock_field.empty_label = ""
        mock_field.label_from_instance = lambda o: str(o)
        mock_field.prepare_value = lambda o: o.pk
        mock_field.queryset = Vat.objects.all()
        it = ModelChoiceIteratorWithFields(mock_field)
        it = iter(it)
        widget = SelectWithDataAttr(choices=it, attrs={"data-option-attrs": ["rate"]})
        widget_html = widget.render("vat", vat.pk)
        self.assertHTMLEqual(
            widget_html,
            f"""<select name="vat">
            <option value=""></option>

            <option value="{vat.pk}" selected data-rate="20.00">1 - standard - 20.00%</option>

            </select>"""
        )
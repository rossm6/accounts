from datetime import date

import mock
from accountancy.forms import BaseAjaxFormMixin, BaseTransactionMixin
from contacts.models import Contact
from django import forms
from django.test import TestCase
from purchases.models import PurchaseHeader, Supplier


class BaseAjaxFormMixinTestsForNonModelForm(TestCase):

    @classmethod
    def setUpTestData(cls):
        contacts = []
        for i in range(10):
            c = Contact(code=i, name="duh")
            contacts.append(c)
        Contact.objects.bulk_create(contacts)

    def test_without_data(self):
        class Form(BaseAjaxFormMixin, forms.Form):
            contacts = forms.ModelChoiceField(
                queryset=Contact.objects.all()
            )

            class Meta:
                ajax_fields = {
                    "contacts": {}
                }

        f = Form()
        self.assertEqual(
            len(f.fields["contacts"].queryset),
            0
        )
        self.assertEqual(
            len(f.fields["contacts"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["contacts"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["contacts"].empty_label,
            None
        )

    def test_with_data(self):
        class Form(BaseAjaxFormMixin, forms.Form):
            contacts = forms.ModelChoiceField(
                queryset=Contact.objects.all()
            )

            class Meta:
                ajax_fields = {
                    "contacts": {}
                }

        f = Form(data=mock.Mock())
        self.assertEqual(
            len(f.fields["contacts"].queryset),
            10
        )
        self.assertEqual(
            len(f.fields["contacts"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["contacts"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["contacts"].empty_label,
            None
        )

    def test_full_clean_when_data_is_invalid_with_no_empty_label_defined(self):
        contact = Contact.objects.first()

        class Form(BaseAjaxFormMixin, forms.Form):
            contacts = forms.ModelChoiceField(
                queryset=Contact.objects.all()
            )

            class Meta:
                ajax_fields = {
                    "contacts": {}
                }
        f = Form(data={"contacts": "dsfdsfdsf"})
        self.assertEqual(
            len(f.fields["contacts"].choices),
            10
        )
        f.is_valid()
        choices = f.fields["contacts"].choices
        self.assertEqual(
            len(choices),
            1
        )
        choice = choices[0]
        value, label = choice
        self.assertEqual(
            value,
            None
        )
        self.assertEqual(
            label,
            ""
        )

    def test_full_clean_when_data_is_invalid_with_empty_label_defined(self):
        contact = Contact.objects.first()

        class Form(BaseAjaxFormMixin, forms.Form):
            contacts = forms.ModelChoiceField(
                queryset=Contact.objects.all()
            )

            class Meta:
                ajax_fields = {
                    "contacts": {
                        "empty_label": "DUH"
                    }
                }
        f = Form(data={"contacts": "dsfdsfdsf"})
        self.assertEqual(
            len(f.fields["contacts"].choices),
            11  # includes empty label
        )
        f.is_valid()
        choices = f.fields["contacts"].choices
        self.assertEqual(
            len(choices),
            1
        )
        choice = choices[0]
        value, label = choice
        self.assertEqual(
            value,
            None
        )
        self.assertEqual(
            label,
            "DUH"
        )

    def test_full_clean_when_data_is_valid(self):
        contact = Contact.objects.first()

        class Form(BaseAjaxFormMixin, forms.Form):
            contacts = forms.ModelChoiceField(
                queryset=Contact.objects.all()
            )

            class Meta:
                ajax_fields = {
                    "contacts": {}
                }
        f = Form(data={"contacts": contact.pk})
        self.assertEqual(
            len(f.fields["contacts"].choices),
            10
        )
        f.is_valid()
        choices = f.fields["contacts"].choices
        self.assertEqual(
            len(choices),
            1
        )
        value, label = choices[0]
        self.assertEqual(
            str(contact.pk),
            str(value)
        )
        self.assertEqual(
            str(contact),
            label
        )


class BaseAjaxFormMixinTestsForModalForm(TestCase):

    @classmethod
    def setUpTestData(cls):
        contacts = []
        for i in range(10):
            c = Contact(code=i, name="duh")
            contacts.append(c)
        Contact.objects.bulk_create(contacts)

    def test_without_data(self):

        class Form(BaseAjaxFormMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("supplier",)
                ajax_fields = {
                    "supplier": {}
                }

        f = Form()
        self.assertEqual(
            len(f.fields["supplier"].queryset),
            0
        )
        self.assertEqual(
            len(f.fields["supplier"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["supplier"].empty_label,
            None
        )

    def test_with_instance(self):

        supplier = Supplier.objects.first()

        instance = PurchaseHeader.objects.create(
            supplier=supplier,
            date=date.today(),
            ref="1"
        )

        class Form(BaseAjaxFormMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("supplier",)
                ajax_fields = {
                    "supplier": {}
                }

        f = Form(instance=instance)

        self.assertEqual(
            len(f.fields["supplier"].queryset),
            1
        )
        self.assertEqual(
            f.fields["supplier"].queryset[0],
            supplier
        )
        self.assertEqual(
            len(f.fields["supplier"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["supplier"].empty_label,
            None
        )

    def test_with_data_and_no_instance(self):

        class Form(BaseAjaxFormMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("supplier",)
                ajax_fields = {
                    "supplier": {}
                }

        f = Form(data=mock.Mock())
        self.assertEqual(
            len(f.fields["supplier"].queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["supplier"].empty_label,
            None
        )

    def test_with_instance_and_data(self):

        supplier = Supplier.objects.first()

        instance = PurchaseHeader.objects.create(
            supplier=supplier,
            date=date.today(),
            ref="1"
        )

        class Form(BaseAjaxFormMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("supplier",)
                ajax_fields = {
                    "supplier": {}
                }

        f = Form(instance=instance, data=mock.Mock())
        self.assertEqual(
            len(f.fields["supplier"].queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].load_queryset),
            10
        )
        self.assertEqual(
            len(f.fields["supplier"].post_queryset),
            10
        )
        self.assertEqual(
            f.fields["supplier"].empty_label,
            None
        )


class BaseTransactionMixinTests(TestCase):
    """
    I was going to mock out everything but i got stuck with the
    isintance call.

    Mocking the UIDecimalField with mock.patch is no good because it returns
    an instance of mock.Mock, and the second argument of isinstance must be a
    class.
    """

    def test_with_no_instance_and_no_initial(self):

        class TestForm(BaseTransactionMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("total",)

        with mock.patch.object(forms.ModelForm, "__init__") as mocked_init:
            t = TestForm()
            self.assertTrue(mocked_init.called)

    def test_with_instance_but_no_initial_for_positive_tran_type(self):

        class TestForm(BaseTransactionMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("total",)

        supplier = Supplier.objects.create(code="1", name="1")
        instance = PurchaseHeader.objects.create(
            type="pi",
            supplier=supplier,
            ref="1",
            date=date.today(),
            total=120
        )

        with mock.patch.object(forms.ModelForm, "__init__") as mocked_init:
            t = TestForm(instance=instance)
            self.assertTrue(mocked_init.called)
            args, kwargs = mocked_init.call_args_list[0]
            self.assertEqual(
                kwargs["initial"],
                {
                    "total": 120
                }
            )

    def test_with_instance_but_no_initial_for_negative_tran_type(self):

        class TestForm(BaseTransactionMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("total",)

        supplier = Supplier.objects.create(code="1", name="1")
        instance = PurchaseHeader.objects.create(
            type="pc",
            supplier=supplier,
            ref="1",
            date=date.today(),
            total=-120
        )

        with mock.patch.object(forms.ModelForm, "__init__") as mocked_init:
            t = TestForm(instance=instance)
            self.assertTrue(mocked_init.called)
            args, kwargs = mocked_init.call_args_list[0]
            self.assertEqual(
                kwargs["initial"],
                {
                    "total": 120
                }
            )

    def test_with_instance_and_initial(self):

        class TestForm(BaseTransactionMixin, forms.ModelForm):
            class Meta:
                model = PurchaseHeader
                fields = ("total",)

        supplier = Supplier.objects.create(code="1", name="1")
        instance = PurchaseHeader.objects.create(
            type="pc",
            supplier=supplier,
            ref="1",
            date=date.today(),
            total=-120
        )

        with mock.patch.object(forms.ModelForm, "__init__") as mocked_init:
            t = TestForm(instance=instance, initial={"total": 999})
            self.assertTrue(mocked_init.called)
            args, kwargs = mocked_init.call_args_list[0]
            self.assertEqual(
                kwargs["initial"],
                {
                    "total": 999
                }
            )
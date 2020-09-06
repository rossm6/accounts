from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import (APIRequestFactory, APITestCase,
                                 force_authenticate)

from accountancy.testing.helpers import create_formset_data, create_header
from nominals.models import Nominal
from vat.models import Vat

from ..views import CreateNominalJournal

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
PERIOD = '202007'


class APITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ref = "test journal"
        cls.date = datetime.now().strftime('%Y-%m-%d')
        cls.due_date = (datetime.now() + timedelta(days=31)
                        ).strftime('%Y-%m-%d')
        cls.description = "a line description"

        # ASSETS
        assets = Nominal.objects.create(name="Assets")
        current_assets = Nominal.objects.create(
            parent=assets, name="Current Assets")
        cls.bank_nominal = Nominal.objects.create(
            parent=current_assets, name="Bank Account")
        cls.debtors_nominal = Nominal.objects.create(
            parent=current_assets, name="Trade Debtors")

        # LIABILITIES
        liabilities = Nominal.objects.create(name="Liabilities")
        current_liabilities = Nominal.objects.create(
            parent=liabilities, name="Current Liabilities")
        cls.vat_nominal = Nominal.objects.create(
            parent=current_assets, name="Vat")

        cls.vat_code = Vat.objects.create(
            code="1", name="standard rate", rate=20)

        cls.user = get_user_model().objects.create_user(
            username="ross",
            password="Test123!"
        )

    def test_create_journal(self):
        factory = APIRequestFactory()
        header_data = create_header(HEADER_FORM_PREFIX, {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": 120,
            "period": PERIOD
        })
        line_forms = []
        line_forms.append(
            {
                "description": self.description,
                "goods": 100,
                "nominal": self.bank_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": 20
            }
        )
        line_forms.append(
            {
                "description": self.description,
                "goods": -100,
                "nominal": self.debtors_nominal.pk,
                "vat_code": self.vat_code.pk,
                "vat": -20
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        data = {}
        data.update(header_data)
        data.update(line_data)
        request = factory.post(
            reverse("nominals:nominal-transaction-create"), data)
        # data is sent in the same way the browser does i.e. multipart
        force_authenticate(request, user=self.user)
        response = CreateNominalJournal.as_view()(request)
        print(response)

from datetime import datetime, timedelta
from json import loads

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import (APIRequestFactory, APITestCase,
                                 force_authenticate, APIClient)

from accountancy.testing.helpers import create_formset_data, create_header
from nominals.models import Nominal
from vat.models import Vat

from ..views import CreateNominalJournal, EditNominalJournal
from .helpers import create_nominal_journal

HEADER_FORM_PREFIX = "header"
LINE_FORM_PREFIX = "line"
PERIOD = '202007'


"""

The REST framework request factory is used for CREATE but for Edit, for
some unknown reason, the keywords for the url were not being captured
so i ended up using the API client provided by REST.

"""


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

        cls.username = "ross"
        cls.password = "Test123!"

        cls.user = get_user_model().objects.create_user(
            username=cls.username,
            password=cls.password
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
        self.assertEqual(response.status_code, 200)
        data = loads(response.content)
        header = data["header"]
        self.assertEqual(
            header["ref"],
            self.ref
        )
        self.assertEqual(
            header["goods"],
            '100.00'
        )
        self.assertEqual(
            header["vat"],
            '20.00'
        )
        self.assertEqual(
            header["total"],
            '120.00'
        )
        self.assertEqual(
            header["date"],
            str(self.date)
        )
        self.assertEqual(
            header["period"],
            PERIOD
        )
        self.assertEqual(
            header["status"],
            'c'
        )
        self.assertEqual(
            header["type"],
            'nj'
        )
        lines = data["lines"]
        # LINE 1
        self.assertEqual(
            lines[0]["line_no"],
            1
        )
        self.assertEqual(
            lines[0]["description"],
            "a line description"
        )
        self.assertEqual(
            lines[0]["goods"],
            "100.00"
        )
        self.assertEqual(
            lines[0]["vat"],
            "20.00"
        )
        self.assertEqual(
            lines[0]["nominal"],
            self.bank_nominal.pk
        )
        self.assertEqual(
            lines[0]["vat_code"],
            self.vat_code.pk
        )
        # LINE 2
        self.assertEqual(
            lines[1]["line_no"],
            2
        )
        self.assertEqual(
            lines[1]["description"],
            "a line description"
        )
        self.assertEqual(
            lines[1]["goods"],
            "-100.00"
        )
        self.assertEqual(
            lines[1]["vat"],
            "-20.00"
        )
        self.assertEqual(
            lines[1]["nominal"],
            self.debtors_nominal.pk
        )
        self.assertEqual(
            lines[1]["vat_code"],
            self.vat_code.pk
        )
        nom_trans = data["nom_trans"]

        goods = nom_trans[::2]
        vat = nom_trans[1::2]

        for i, nom_tran in enumerate(goods):
            self.assertEqual(
                nom_tran["module"],
                "NL"
            )
            self.assertEqual(
                nom_tran["header"],
                header["id"],
            )
            self.assertEqual(
                nom_tran["line"],
                lines[i]["id"]
            )
            self.assertEqual(
                nom_tran["value"],
                lines[i]["goods"]
            )
            self.assertEqual(
                nom_tran["ref"],
                header["ref"]
            )
            self.assertEqual(
                nom_tran["period"],
                PERIOD
            )
            self.assertEqual(
                nom_tran["date"],
                header["date"]
            )
            self.assertEqual(
                nom_tran["field"],
                "g"
            )
            self.assertEqual(
                nom_tran["nominal"],
                lines[i]["nominal"]
            )
            self.assertEqual(
                nom_tran["type"],
                header["type"]
            )

        for i, nom_tran in enumerate(vat):
            self.assertEqual(
                nom_tran["module"],
                "NL"
            )
            self.assertEqual(
                nom_tran["header"],
                header["id"],
            )
            self.assertEqual(
                nom_tran["line"],
                lines[i]["id"]
            )
            self.assertEqual(
                nom_tran["value"],
                lines[i]["vat"]
            )
            self.assertEqual(
                nom_tran["ref"],
                header["ref"]
            )
            self.assertEqual(
                nom_tran["period"],
                PERIOD
            )
            self.assertEqual(
                nom_tran["date"],
                header["date"]
            )
            self.assertEqual(
                nom_tran["field"],
                "v"
            )
            self.assertEqual(
                nom_tran["nominal"],
                self.vat_nominal.pk
            )
            self.assertEqual(
                nom_tran["type"],
                header["type"]
            )

    def test_edit_journal(self):
        factory = APIRequestFactory()

        # create the journal first to edit
        header, lines, nominal_transactions = create_nominal_journal({
            "header": {
                "type": "nj",
                "ref": self.ref,
                "period": PERIOD,
                "date": self.date,
                "total": 120
            },
            "lines": [
                {
                    "line_no": 1,
                    "description": self.description,
                    "goods": 100,
                    "nominal": self.bank_nominal,
                    "vat_code": self.vat_code,
                    "vat": 20
                },
                {
                    "line_no": 2,
                    "description": self.description,
                    "goods": -100,
                    "nominal": self.debtors_nominal,
                    "vat_code": self.vat_code,
                    "vat": -20
                }
            ],
        },
            self.vat_nominal
        )

        header_data = create_header(HEADER_FORM_PREFIX, {
            "type": header.type,
            "ref": header.ref,
            "date": header.date,
            "total": header.total,
            "period": header.period
        })
        line_forms = []
        line_forms.append(
            {
                "id": lines[0].id,
                "description": lines[0].description,
                "goods": lines[0].goods,
                "nominal": lines[0].nominal.pk,
                "vat_code": lines[0].vat_code.pk,
                "vat": lines[0].vat
            }
        )
        line_forms.append(
            {
                "id": lines[1].id,
                "description": lines[1].description,
                "goods": lines[1].goods,
                "nominal": lines[1].nominal.pk,
                "vat_code": lines[1].vat_code.pk,
                "vat": lines[1].vat
            }
        )
        line_data = create_formset_data(LINE_FORM_PREFIX, line_forms)
        line_data["line-INITIAL_FORMS"] = 2
        data = {}
        data.update(header_data)
        data.update(line_data)

        client = APIClient()
        self.client.login(
            username=self.username,
            password=self.password
        )
        response = self.client.post(
            reverse(
                "nominals:nominal-transaction-edit", kwargs={"pk": header.pk}
            ),
            data
        )
        self.assertEqual(response.status_code, 200)
        data = loads(response.content)
        header = data["header"]
        self.assertEqual(
            header["ref"],
            self.ref
        )
        self.assertEqual(
            header["goods"],
            '100.00'
        )
        self.assertEqual(
            header["vat"],
            '20.00'
        )
        self.assertEqual(
            header["total"],
            '120.00'
        )
        self.assertEqual(
            header["date"],
            str(self.date)
        )
        self.assertEqual(
            header["period"],
            PERIOD
        )
        self.assertEqual(
            header["status"],
            'c'
        )
        self.assertEqual(
            header["type"],
            'nj'
        )
        lines = data["lines"]
        # LINE 1
        self.assertEqual(
            lines[0]["line_no"],
            1
        )
        self.assertEqual(
            lines[0]["description"],
            "a line description"
        )
        self.assertEqual(
            lines[0]["goods"],
            "100.00"
        )
        self.assertEqual(
            lines[0]["vat"],
            "20.00"
        )
        self.assertEqual(
            lines[0]["nominal"],
            self.bank_nominal.pk
        )
        self.assertEqual(
            lines[0]["vat_code"],
            self.vat_code.pk
        )
        # LINE 2
        self.assertEqual(
            lines[1]["line_no"],
            2
        )
        self.assertEqual(
            lines[1]["description"],
            "a line description"
        )
        self.assertEqual(
            lines[1]["goods"],
            "-100.00"
        )
        self.assertEqual(
            lines[1]["vat"],
            "-20.00"
        )
        self.assertEqual(
            lines[1]["nominal"],
            self.debtors_nominal.pk
        )
        self.assertEqual(
            lines[1]["vat_code"],
            self.vat_code.pk
        )
        nom_trans = data["nom_trans"]

        goods = nom_trans[::2]
        vat = nom_trans[1::2]

        for i, nom_tran in enumerate(goods):
            self.assertEqual(
                nom_tran["module"],
                "NL"
            )
            self.assertEqual(
                nom_tran["header"],
                header["id"],
            )
            self.assertEqual(
                nom_tran["line"],
                lines[i]["id"]
            )
            self.assertEqual(
                nom_tran["value"],
                lines[i]["goods"]
            )
            self.assertEqual(
                nom_tran["ref"],
                header["ref"]
            )
            self.assertEqual(
                nom_tran["period"],
                PERIOD
            )
            self.assertEqual(
                nom_tran["date"],
                header["date"]
            )
            self.assertEqual(
                nom_tran["field"],
                "g"
            )
            self.assertEqual(
                nom_tran["nominal"],
                lines[i]["nominal"]
            )
            self.assertEqual(
                nom_tran["type"],
                header["type"]
            )

        for i, nom_tran in enumerate(vat):
            self.assertEqual(
                nom_tran["module"],
                "NL"
            )
            self.assertEqual(
                nom_tran["header"],
                header["id"],
            )
            self.assertEqual(
                nom_tran["line"],
                lines[i]["id"]
            )
            self.assertEqual(
                nom_tran["value"],
                lines[i]["vat"]
            )
            self.assertEqual(
                nom_tran["ref"],
                header["ref"]
            )
            self.assertEqual(
                nom_tran["period"],
                PERIOD
            )
            self.assertEqual(
                nom_tran["date"],
                header["date"]
            )
            self.assertEqual(
                nom_tran["field"],
                "v"
            )
            self.assertEqual(
                nom_tran["nominal"],
                self.vat_nominal.pk
            )
            self.assertEqual(
                nom_tran["type"],
                header["type"]
            )

    def test_create_journal_with_non_form_error_for_line_formset(self):
        """
        Check that form errors for line formsets are picked up
        """

        factory = APIRequestFactory()
        header_data = create_header(HEADER_FORM_PREFIX, {
            "type": "nj",
            "ref": self.ref,
            "date": self.date,
            "total": 140,
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
        self.assertEqual(response.status_code, 400)
        data = loads(response.content)
        self.assertEqual(
            data,
            {'message': 'The total of the debits does not equal the total you entered.',
                'code': 'invalid-total'}
        )

    def test_create_journal_with_line_form_error(self):
        """
        Check that form errors for line formsets are picked up
        """

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
                "nominal": 999999999999999,  # NON EXISTENT NOMINAL CODE
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
        self.assertEqual(response.status_code, 400)
        data = loads(response.content)
        self.assertEqual(
            data,
            {
                'nominal': [
                    {'message': 'Select a valid choice. That choice is not one of the available choices.',
                        'code': 'invalid_choice'}
                ]
            }
        )

from datetime import timedelta

from django.utils import timezone

from cashbook.models import CashBookTransaction
from nominals.models import NominalTransaction
from utils.helpers import sort_multiple

from .models import PurchaseHeader, PurchaseLine, Supplier

PERIOD = '202007'


def create_formset_data(prefix, forms):
    data = {}
    for i, form in enumerate(forms):
        for field in form:
            data[
                prefix + "-" + str(i) + "-" + field
            ] = form[field]
    if forms:
        i = i + 1  # pk keys start
    else:
        i = 0
    management_form = {
        prefix + "-TOTAL_FORMS": i,
        prefix + "-INITIAL_FORMS": 0,
        prefix + "-MIN_NUM_FORMS": 0,
        prefix + "-MAX_NUM_FORMS": 1000
    }
    data.update(management_form)
    return data


def create_header(prefix, form):
    data = {}
    for field in form:
        data[prefix + "-" + field] = form[field]
    data[prefix + "-" + "period"] = PERIOD
    return data


# because Heroku doesn't have one unlike my local Linux OS
common_words_dictionary = [
    "A",
    "A's",
    "AMD",
    "AMD's",
    "AOL",
    "AOL's",
    "Aachen",
    "Aachen's",
    "Aaliyah",
    "Aaliyah's",
    "Aaron",
    "Aaron's",
    "Abbas",
    "Abbas's",
    "Abbasid",
    "Abbasid's",
    "Abbott",
    "Abbott's",
    "Abby",
    "Abby's",
    "Abdul",
    "Abdul's",
    "Abe",
    "Abe's",
    "Abel",
    "Abel's",
    "Abelard",
    "Abelard's",
    "Abelson",
    "Abelson's",
    "Aberdeen",
    "Aberdeen's",
    "Abernathy",
    "Abernathy's",
    "Abidjan",
    "Abidjan's",
    "Abigail",
    "Abigail's",
    "Abilene",
    "Abilene's",
    "Abner",
    "Abner's",
    "Abraham",
    "Abraham's",
    "Abram",
    "Abram's",
    "Abrams",
    "Abrams's",
    "Absalom",
    "Absalom's",
    "Abuja",
    "Abuja's",
    "Abyssinia",
    "Abyssinia's",
    "Abyssinian",
    "Abyssinian's",
    "Ac",
    "Ac's",
    "Acadia",
    "Acadia's",
    "Acapulco",
    "Acapulco's",
    "Accenture",
    "Accenture's",
    "Accra",
    "Accra's",
    "Acevedo",
    "Acevedo's",
    "Achaean",
    "Achaean's",
    "Achebe",
    "Achebe's",
    "Achernar",
    "Achernar's",
    "Acheson",
    "Acheson's",
    "Achilles",
    "Achilles's",
    "Aconcagua",
    "Aconcagua's",
    "Acosta",
    "Acosta's",
    "Acropolis",
    "Acrux",
    "Acrux's",
    "Actaeon",
    "Actaeon's",
    "Acton",
    "Acton's",
    "Acts",
    "Acts's",
    "Acuff",
    "Acuff's",
    "Ada",
    "Ada's",
    "Adam",
    "Adam's",
    "Adams",
    "Adams's",
    "Adan",
    "Adan's",
    "Adana",
    "Adana's",
    "Adar",
    "Adar's",
    "Addams",
    "Addams's",
    "Adderley",
    "Adderley's",
    "Addie",
    "Addie's",
    "Addison",
    "Addison's",
    "Adela",
    "Adela's",
    "Adelaide",
    "Adelaide's",
    "Adele",
    "Adele's",
    "Adeline",
    "Adeline's",
    "Aden",
    "Aden's",
    "Adenauer",
    "Adenauer's",
    "Adhara"
]


def create_suppliers(n):
    suppliers = []
    i = 0

    for word in common_words_dictionary:
        for word in dictionary:
            suppliers.append(
                Supplier(name=word, code=str(i))
            )
            if i > n:
                break
            i = i + 1
    return Supplier.objects.bulk_create(suppliers)


def create_default_data():
    create_suppliers(1000)


def create_lines(header, lines):
    tmp = []
    for i, line in enumerate(lines):
        line["line_no"] = i + 1
        line["header"] = header
        tmp.append(PurchaseLine(**line))
    return PurchaseLine.objects.bulk_create(tmp)


def create_invoices(supplier, ref_prefix, n, value=100):
    date = timezone.now()
    due_date = date + timedelta(days=31)
    invoices = []
    for i in range(n):
        i = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            goods=value,
            vat=0.2 * value,
            total=1.2 * value,
            paid=0,
            due=1.2 * value,
            date=date,
            due_date=due_date,
            type="pi",
            period=PERIOD
        )
        invoices.append(i)
    return PurchaseHeader.objects.bulk_create(invoices)


def create_invoice_with_lines(header, lines):
    header = PurchaseHeader.objects.create(**header)
    lines = create_lines(header, lines)
    return header, lines


def create_credit_note_with_lines(header, lines):
    header["paid"] *= -1
    header["total"] *= -1
    header["due"] *= -1
    header = PurchaseHeader.objects.create(**header)
    # this assumes lines[n] is line[0] for all n
    lines[0]["goods"] *= -1
    lines[0]["vat"] *= -1
    lines = create_lines(header, lines)
    return header, lines


def create_payments(supplier, ref_prefix, n, value=100):
    date = timezone.now()
    due_date = date + timedelta(days=31)
    payments = []
    for i in range(n):
        p = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            total=-1 * value,
            paid=0,
            due=-1 * value,
            date=date,
            type="pp",
            period=PERIOD
        )
        payments.append(p)
    return PurchaseHeader.objects.bulk_create(payments)


def create_invoice_with_nom_entries(header, lines, vat_nominal, control_nominal):
    header = PurchaseHeader.objects.create(**header)
    lines = create_lines(header, lines)
    nom_trans = []
    for line in lines:
        if line.goods:
            nom_trans.append(
                NominalTransaction(
                    module="PL",
                    header=header.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=line.goods,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="g",
                    type=header.type
                )
            )
        if line.vat:
            nom_trans.append(
                NominalTransaction(
                    module="PL",
                    header=header.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=line.vat,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="v",
                    type=header.type
                )
            )
        if line.goods or line.vat:
            nom_trans.append(
                NominalTransaction(
                    module="PL",
                    header=header.pk,
                    line=line.pk,
                    nominal=control_nominal,
                    value=-1 * (line.goods + line.vat),
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="t",
                    type=header.type
                )
            )
    nom_trans = NominalTransaction.objects.bulk_create(nom_trans)
    nom_trans = sort_multiple(nom_trans, *[(lambda n: n.line, False)])
    goods_and_vat = nom_trans[:-1]
    for i, line in enumerate(lines):
        line.goods_nominal_transaction = nom_trans[3 * i]
        line.vat_nominal_transaction = nom_trans[(3 * i) + 1]
        line.total_nominal_transaction = nom_trans[(3 * i) + 2]
    PurchaseLine.objects.bulk_update(
        lines,
        ["goods_nominal_transaction", "vat_nominal_transaction",
            "total_nominal_transaction"]
    )
    return header


def create_payment_with_nom_entries(header, control_nominal, bank_nominal):
    header["total"] *= -1
    header["due"] *= -1
    header["paid"] *= -1
    header["goods"] = 0
    header["vat"] = 0
    header = PurchaseHeader.objects.create(**header)
    if header.total != 0:
        nom_trans = []
        nom_trans.append(
            NominalTransaction(
                module="PL",
                header=header.pk,
                line=1,
                nominal=bank_nominal,
                value=header.total,
                ref=header.ref,
                period=header.period,
                date=header.date,
                field="t",
                type=header.type
            )
        )
        nom_trans.append(
            NominalTransaction(
                module="PL",
                header=header.pk,
                line=2,
                nominal=control_nominal,
                value=-1 * header.total,
                ref=header.ref,
                period=header.period,
                date=header.date,
                field="t",
                type=header.type
            )
        )
        nom_trans = NominalTransaction.objects.bulk_create(nom_trans)
        CashBookTransaction.objects.create(
            module="PL",
            header=header.pk,
            line=1,
            cash_book=header.cash_book,
            value=header.total,
            ref=header.ref,
            period=header.period,
            date=header.date,
            field="t",
            type=header.type
        )
        return header


def create_refund_with_nom_entries(header, control_nominal, bank_nominal):
    # positive inputted, turn negative, then turned positive again in create_payment_with_nom
    header["total"] *= -1
    header["due"] *= -1
    header["paid"] *= -1
    # done this way because i created other function first
    return create_payment_with_nom_entries(header, control_nominal, bank_nominal)


def create_credit_note_with_nom_entries(header, lines, vat_nominal, control_nominal):
    header["total"] = -1 * header["total"]
    header["due"] = -1 * header["due"]
    header["paid"] = -1 * header["paid"]
    # lines is assumed to be of form [ {} ] * N
    # thus each object is in fact the same object in memory
    lines[0]["goods"] = -1 * lines[0]["goods"]
    lines[0]["vat"] = -1 * lines[0]["vat"]
    return create_invoice_with_nom_entries(header, lines, vat_nominal, control_nominal)

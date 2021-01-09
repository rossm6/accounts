from accountancy.helpers import sort_multiple
from django.utils import timezone
from vat.models import VatTransaction

from nominals.models import (Nominal, NominalHeader, NominalLine,
                             NominalTransaction)


def create_nominal_journal_without_nom_trans(journal):
    header = NominalHeader(**journal["header"])
    header.save()
    lines = []
    for line in journal["lines"]:
        line["header"] = header
        line = NominalLine(**line)
        lines.append(line)
    lines = NominalLine.objects.bulk_create(lines)
    return header, lines


def create_nominal_journal(journal, vat_nominal):
    header, lines = create_nominal_journal_without_nom_trans(journal)
    nominal_transactions = []
    for line in lines:
        tran = {
            "module": "NL",
            "header": header.pk,
            "line": line.pk,
            "nominal": line.nominal,
            "value": line.goods,
            "ref": header.ref,
            "period": header.period,
            "type": header.type,
            "date": timezone.now(),
            "field": "g"
        }
        tran = NominalTransaction(**tran)
        nominal_transactions.append(tran)
        if line.vat:
            tran = {
                "module": "NL",
                "header": header.pk,
                "line": line.pk,
                "nominal": vat_nominal,
                "value": line.vat,
                "ref": header.ref,
                "period": header.period,
                "type": header.type,
                "date": timezone.now(),
                "field": "v"
            }
            tran = NominalTransaction(**tran)
            nominal_transactions.append(tran)
    trans = NominalTransaction.objects.bulk_create(nominal_transactions)
    # THIS IS CRAZILY INEFFICIENT !!!!
    for line in lines:
        line_nominal_trans = {
            tran.field: tran
            for tran in trans
            if tran.line == line.pk
        }
        line.add_nominal_transactions(line_nominal_trans)
    NominalLine.objects.bulk_update(
        lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])
    return header, lines, trans


def create_vat_transactions(header, lines):
    vat_trans = []
    for line in lines:
        vat_trans.append(
            VatTransaction(
                header=header.pk,
                line=line.pk,
                module="NL",
                ref=header.ref,
                period=header.period,
                date=header.date,
                field="v",
                tran_type=header.type,
                vat_type=header.vat_type,
                vat_code=line.vat_code,
                vat_rate=line.vat_code.rate,
                goods=line.goods,
                vat=line.vat
            )
        )
    vat_trans = VatTransaction.objects.bulk_create(vat_trans)
    vat_trans = sort_multiple(vat_trans, *[(lambda v: v.line, False)])
    lines = sort_multiple(lines, *[(lambda l: l.pk, False)])
    for i, line in enumerate(lines):
        line.vat_transaction = vat_trans[i]
    NominalLine.objects.bulk_update(lines, ["vat_transaction"])

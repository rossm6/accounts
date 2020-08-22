from django.utils import timezone

from ..models import NominalHeader, NominalLine, NominalTransaction

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
            tran.field : tran
            for tran in trans
            if tran.line == line.pk 
        }
        line.add_nominal_transactions(line_nominal_trans)
    NominalLine.objects.bulk_update(lines, ['goods_nominal_transaction', 'vat_nominal_transaction'])
    return header, lines, trans

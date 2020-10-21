from accountancy.helpers import sort_multiple
from cashbook.models import CashBookLine
from nominals.models import NominalTransaction
from vat.models import VatTransaction


def create_lines(line_cls, header, lines):
    # DO WE NEED THIS?
    tmp = []
    for i, line in enumerate(lines):
        line["line_no"] = i + 1
        line["header"] = header
        tmp.append(line_cls(**line))
    return line_cls.objects.bulk_create(tmp)


def create_nom_trans(nom_tran_cls, line_cls, header, lines, bank_nominal, vat_nominal):
    nom_trans = []
    for line in lines:
        if line.goods:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=-1 * line.goods,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="g",
                    type=header.type
                )
            )
        if line.vat:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=-1 * line.vat,
                    ref=header.ref,
                    period=header.period,
                    date=header.date,
                    field="v",
                    type=header.type
                )
            )
        if line.goods or line.vat:
            nom_trans.append(
                nom_tran_cls(
                    module="CB",
                    header=header.pk,
                    line=line.pk,
                    nominal=bank_nominal,
                    value=line.goods + line.vat,
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
    line_cls.objects.bulk_update(
        lines,
        ["goods_nominal_transaction", "vat_nominal_transaction",
            "total_nominal_transaction"]
    )


def create_cash_book_trans(cash_book_tran_cls, header):
    cash_book_tran_cls.objects.create(
        module="CB",
        header=header.pk,
        line=1,
        value=header.total,
        ref=header.ref,
        period=header.period,
        date=header.date,
        field="t",
        cash_book=header.cash_book,
        type=header.type
    )


def create_vat_transactions(header, lines):
    vat_trans = []
    for line in lines:
        vat_trans.append(
            VatTransaction(
                header=header.pk,
                line=line.pk,
                module="CB",
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
    CashBookLine.objects.bulk_update(lines, ["vat_transaction"])

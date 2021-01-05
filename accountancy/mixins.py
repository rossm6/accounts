from itertools import groupby
from uuid import uuid4

from django.conf import settings
from simple_history import register
from simple_history.models import HistoricalRecords
from simple_history.signals import pre_create_historical_record

from accountancy.helpers import (
    DELETED_HISTORY_TYPE, create_historical_records,
    disconnect_simple_history_receiver_for_post_delete_signal,
    get_all_historical_changes)
from accountancy.signals import audit_post_delete


def zeus(sender, **kwargs):
    print(sender)
    print(kwargs)


class AuditMixin:
    """

    IMPORTANT - This class must come before models.Model (i.e. to the left of this class) so that delete is
    called on this class first.

    `simple_history` is the django package used to audit.  It does not provide a way of auditing for bulk
    deletion however.  The solution is easy enough but we must remember to disconnect the simple_history post_delete
    receiver for the model being audited so that it does receive the post_delete signal;
    otherwise for every item deleted in the bulk delete a post-delete signal is fired which
    creates another audit log !!!

    We then provide our own signal which is fired when delete is called for a model instance but it is not fired
    when we bulk_delete.

    Subclasses should therefore do the following (now this is done automatically in simple_history_custom_set_up) -

        E.g.

            class Contact(Audit, models.Model):
                pass


            # this means simple_history will track the changes
            register(Contact)
            disconnect_simple_history_receiver_for_post_delete_signal(Contact)
            audit_post_delete.connect(
                Contact.post_delete, sender=Contact, dispatch_uid=uuid4())


    Then we can safely do -

        bulk_delete_with_history([contact_instances])

    """

    @classmethod
    def simple_history_custom_set_up(cls):
        """
        See note in class definition for explanation.

        This should be called in AppConfig.ready
        """
        register(cls)
        disconnect_simple_history_receiver_for_post_delete_signal(cls)
        audit_post_delete.connect(
            cls.post_delete, sender=cls, dispatch_uid=uuid4())
        pre_create_historical_record.connect(zeus, sender=HistoricalRecords)

    @classmethod
    def post_delete(cls, sender, instance, **kwargs):
        return create_historical_records([instance], instance._meta.model, DELETED_HISTORY_TYPE)

    def delete(self):
        audit_post_delete.send(sender=self._meta.model, instance=self)
        super().delete()

    def ready(self):
        """
        Called by <app_name>.apps.<app_name>Config.
        """
        print("APP READY")
        models = list(self.get_models())  # use up generator
        # otherwise it complains about dict changing size
        for model in models:
            if hasattr(model, "simple_history_custom_set_up"):
                model.simple_history_custom_set_up()


class SingleObjectAuditDetailViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        audit_records = self.model.history.filter(
            **{
                self.model._meta.pk.name: self.object.pk
            }
        ).order_by("pk")
        kwargs = {}
        if hasattr(self, "ui_audit_fields"):
            kwargs["ui_audit_fields"] = self.ui_audit_fields
        changes = get_all_historical_changes(audit_records, **kwargs)
        context["audits"] = changes
        return context


class ResponsivePaginationMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_number = context["page_obj"].number
        page_range = [i for i in range(
            page_number - 5, page_number + 5) if i > 0]
        context["page_range"] = page_range
        context["lower_page_on_xs"] = page_number - 3
        context["upper_range_on_xs"] = page_number + 3
        return context


class VatTransactionMixin:
    """

    To be mixed with the Transaction class.

    Like the nominal transactions, create a vat transaction per line.

    In Vat transaction enquiry we will need to group by -

        module
        header
        vat_code

    """

    def _create_vat_transaction_for_line(self, line, vat_tran_cls):
        if line.vat_code:
            # by virtue of choosing a vat code you want it on the vat return
            # so leaving vat_code blank is the same as choosing N / A
            return vat_tran_cls(
                module=self.module,
                header=self.header_obj.pk,
                line=line.pk,
                goods=line.goods,
                vat=line.vat,
                ref=self.header_obj.ref,
                period=self.header_obj.period,
                date=self.header_obj.date,
                tran_type=self.header_obj.type,
                vat_type=self.vat_type,
                vat_code=line.vat_code,
                vat_rate=line.vat_code.rate,
                field="v"
            )

    def create_vat_transactions(self, vat_tran_cls, **kwargs):
        vat_transactions = []
        if lines := kwargs.get('lines'):
            lines = sorted(lines, key=lambda l: l.pk)
            for line in lines:
                if (vat_transaction := self._create_vat_transaction_for_line(
                    line, vat_tran_cls
                )):
                    vat_transactions.append(vat_transaction)
            if vat_transactions:
                vat_transactions = vat_tran_cls.objects.bulk_create(
                    vat_transactions)
                vat_transactions = sorted(
                    vat_transactions, key=lambda n: n.line)
                line_pk_map = {line.pk: line for line in lines}
                for vat_tran in vat_transactions:
                    # one to one relationship
                    line = line_pk_map[vat_tran.line]
                    line.vat_transaction = vat_tran
                line_cls = kwargs.get('line_cls')
                # not all the lines will necessarily have vat transactions but just update all of them anyway
                line_cls.objects.audited_bulk_update(
                    lines, ['vat_transaction'])

    def _edit_vat_transaction_for_line(self, vat_tran, line):
        if line.vat_code:
            # notice vat_type is updated outside this method
            vat_tran.update_details_from_header(self.header_obj)
            vat_tran.goods = line.goods
            vat_tran.vat = line.vat
            vat_tran.vat_code = line.vat_code
            vat_tran.vat_rate = line.vat_code.rate
            vat_tran.vat_type = self.vat_type
            return
        return vat_tran

    def edit_vat_transactions(self, vat_tran_cls, **kwargs):
        vat_trans_to_update = []
        vat_trans_to_delete = []

        existing_vat_trans = kwargs.get('existing_vat_trans')
        existing_vat_trans = sorted(existing_vat_trans, key=lambda n: n.line)

        if new_lines := kwargs.get("new_lines"):
            sorted(new_lines, key=lambda l: l.pk)
        # this is misleading
        if lines_to_update := kwargs.get("lines_to_update"):
            sorted(lines_to_update, key=lambda l: l.pk)
        if deleted_lines := kwargs.get("deleted_lines"):
            sorted(deleted_lines, key=lambda l: l.pk)

        if lines_to_update:
            lines_to_update_pk = [line.pk for line in lines_to_update]
            vat_trans_to_update = [
                tran for tran in existing_vat_trans if tran.line in lines_to_update_pk]
            vat_trans_to_update = sorted(
                vat_trans_to_update, key=lambda n: n.line)
            line_pk_map = {line.pk: line for line in lines_to_update}
            for vat_tran in vat_trans_to_update:
                line = line_pk_map[vat_tran.line]
                to_delete = self._edit_vat_transaction_for_line(
                    vat_tran, line)
                if to_delete:
                    vat_trans_to_delete.append(to_delete)

        vat_trans_to_update = [
            tran for tran in vat_trans_to_update if tran not in vat_trans_to_delete]

        if deleted_lines:
            lines_to_delete = [line.pk for line in deleted_lines]
            vat_trans_to_delete += [
                tran for tran in existing_vat_trans if tran.line in lines_to_delete]

        line_cls = kwargs.get('line_cls')
        self.create_vat_transactions(
            vat_tran_cls,
            line_cls=line_cls,
            lines=new_lines,
        )
        vat_tran_cls.objects.bulk_update(vat_trans_to_update)
        vat_tran_cls.objects.filter(
            pk__in=[tran.pk for tran in vat_trans_to_delete]).delete()


class BaseNominalTransactionMixin:
    @classmethod
    def get_vat_nominal(cls, nom_cls, **kwargs):
        if (vat_nominal := kwargs.get("vat_nominal")) is None:
            try:
                vat_nominal_name = kwargs.get('vat_nominal_name')
                vat_nominal = nom_cls.objects.get(name=vat_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                vat_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        return vat_nominal

    @classmethod
    def get_control_nominal(cls, nom_cls, **kwargs):
        if (control_nominal := kwargs.get("control_nominal")) is None:
            try:
                control_nominal_name = kwargs.get('control_nominal_name')
                control_nominal = nom_cls.objects.get(
                    name=control_nominal_name)
            except nom_cls.DoesNotExist:
                # bult into system so cannot not exist
                control_nominal = nom_cls.objects.get(
                    name=settings.DEFAULT_SYSTEM_SUSPENSE)
        return control_nominal


class BaseNominalTransactionPerLineMixin:

    def _create_nominal_transactions_for_line(self, nom_tran_cls, line, vat_nominal):
        f = self.header_obj.get_nominal_transaction_factor()
        trans = []
        if line.goods != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=line.nominal,
                    value=f * line.goods,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="g"
                )
            )
        if line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=vat_nominal,
                    value=f * line.vat,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="v"
                )
            )
        return trans

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        vat_nominal = self.get_vat_nominal(nom_cls, **kwargs)
        nominal_transactions = []
        if lines := kwargs.get('lines'):
            lines = sorted(lines, key=lambda l: l.pk)
        for line in lines:
            args = [nom_tran_cls, line, vat_nominal]
            if control_nominal := kwargs.get("control_nominal"):
                args.append(control_nominal)
            nominal_transactions += self._create_nominal_transactions_for_line(
                *args)
        if nominal_transactions:
            nominal_transactions = nom_tran_cls.objects.bulk_create(
                nominal_transactions)
            nominal_transactions = sorted(
                nominal_transactions, key=lambda n: n.line)

            def line_key(n): return n.line
            for line, (key, line_nominal_trans) in zip(lines, groupby(nominal_transactions, line_key)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
                line.add_nominal_transactions(nom_tran_map)
            line_cls = kwargs.get('line_cls')
            fields_to_update = [
                'goods_nominal_transaction', 'vat_nominal_transaction']
            if control_nominal := kwargs.get("control_nominal"):
                fields_to_update.append("total_nominal_transaction")
            line_cls.objects.audited_bulk_update(lines, fields_to_update)
            return nominal_transactions

    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal):
        f = self.header_obj.get_nominal_transaction_factor()
        for tran_field, tran in nom_trans.items():
            tran.update_details_from_header(self.header_obj)
        if 'g' in nom_trans:
            tran = nom_trans["g"]
            tran.nominal = line.nominal
            tran.value = f * line.goods
        if 'v' in nom_trans:
            tran = nom_trans["v"]
            tran.nominal = vat_nominal
            tran.value = f * line.vat
        to_update = []
        to_delete = []
        if 'g' in nom_trans:
            if nom_trans["g"].value:
                to_update.append(nom_trans["g"])
            else:
                to_delete.append(nom_trans["g"])
                line.goods_nominal_transaction = None
        if 'v' in nom_trans:
            if nom_trans["v"].value:
                to_update.append(nom_trans["v"])
            else:
                to_delete.append(nom_trans["v"])
                line.vat_nominal_transaction = None
        return to_update, to_delete

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        vat_nominal = self.get_vat_nominal(nom_cls, **kwargs)
        existing_nom_trans = kwargs.get('existing_nom_trans')
        existing_nom_trans = sorted(existing_nom_trans, key=lambda n: n.line)
        nom_trans_to_update = []
        nom_trans_to_delete = []
        if new_lines := kwargs.get("new_lines"):
            sorted(new_lines, key=lambda l: l.pk)
        if lines_to_update := kwargs.get("lines_to_update"):
            sorted(lines_to_update, key=lambda l: l.pk)
        if deleted_lines := kwargs.get("deleted_lines"):
            sorted(deleted_lines, key=lambda l: l.pk)
        if lines_to_update:
            lines_to_update_pk = [line.pk for line in lines_to_update]
            nom_trans_to_update = [
                tran for tran in existing_nom_trans if tran.line in lines_to_update_pk]
            nom_trans_to_update = sorted(
                nom_trans_to_update, key=lambda n: n.line)
            for line, (key, line_nominal_trans) in zip(lines_to_update, groupby(nom_trans_to_update, key=lambda n: n.line)):
                nom_tran_map = {
                    tran.field: tran for tran in list(line_nominal_trans)}
                args = [nom_tran_map, line, vat_nominal]
                if control_nominal := kwargs.get("control_nominal"):
                    args.append(control_nominal)
                to_update, to_delete = self._edit_nominal_transactions_for_line(
                    *args)
                nom_trans_to_delete += to_delete
        nom_trans_to_update = [
            tran for tran in nom_trans_to_update if tran not in nom_trans_to_delete]
        if deleted_lines:
            lines_to_delete = [line.pk for line in deleted_lines]
            nom_trans_to_delete += [
                tran for tran in existing_nom_trans if tran.line in lines_to_delete]
        line_cls = kwargs.get('line_cls')
        create_kwargs = {
            "line_cls": line_cls,
            "lines": new_lines,
            "vat_nominal": vat_nominal
        }
        if control_nominal := kwargs.get("control_nominal"):
            create_kwargs.update({
                "control_nominal": control_nominal
            })
        self.create_nominal_transactions(
            nom_cls, nom_tran_cls, **create_kwargs)
        nom_tran_cls.objects.bulk_update(nom_trans_to_update)
        nom_tran_cls.objects.filter(
            pk__in=[tran.pk for tran in nom_trans_to_delete]).delete()


class ControlAccountInvoiceTransactionMixin(BaseNominalTransactionPerLineMixin, BaseNominalTransactionMixin):
    """

    The Sales and Purchases Transactions both depend on this.  It creates nominal transactions per line -

        Nominal transaction for the nominal chosen on the line for the value of the goods
        Nominal transaction for the vat control nominal for the value of the vat assuming a vat code is chosen
        Nominal transaction for the control account nominal for the value of the goods plus the vat

    """

    def _create_nominal_transactions_for_line(self, nom_tran_cls, line, vat_nominal, control_nominal):
        """

            Recall,

                PL invoice for 100 goods will need a nominal transaction for 100
                SL invoice for 100 goods will need a nominal transaction for -100
                PL credit for 100 goods will need a nominal transaction for -100
                SL credit for 100 goods will need a nominal transaction for 100

            Likewise,

                PL invoice for -100 goods will need a nominal transaction for -100
                SL invoice for -100 goods will need a nominal transaction for 100
                PL credit for -100 goods will need a nominal transaction for 100
                SL credit for -100 goods will need a nominal transaction for -100


            A positive header is one where it shows on the purchase or sales ledger as a positive, e.g.
            an invoice.

            A negative header is one where it shows on the purchase or sales ledger as a negative e.g.
            a credit note.

            A debit type header is one where a positive goods value debits a nominal e.g. a PL invoice for goods 100.

            A credit type header is one where a positive goods value credit a nominal e.g. a SL invoice for goods 100.

            `f` is therefore the factor for making sure the nominal transaction value has the correct sign based
            on these considerations.

        """
        f = self.header_obj.get_nominal_transaction_factor()
        trans = super()._create_nominal_transactions_for_line(
            nom_tran_cls, line, vat_nominal)
        if line.goods + line.vat != 0:
            trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,
                    line=line.pk,
                    nominal=control_nominal,
                    value=-1 * f * (line.goods + line.vat),
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
        return trans

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        control_nominal = self.get_control_nominal(nom_cls, **kwargs)
        kwargs.update({
            "control_nominal": control_nominal
        })
        return super().create_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)

    def _edit_nominal_transactions_for_line(self, nom_trans, line, vat_nominal, control_nominal):
        """

            Recall,

                PL invoice for 100 goods will need a nominal transaction for 100
                SL invoice for 100 goods will need a nominal transaction for -100
                PL credit for 100 goods will need a nominal transaction for -100
                SL credit for 100 goods will need a nominal transaction for 100

            Likewise,

                PL invoice for -100 goods will need a nominal transaction for -100
                SL invoice for -100 goods will need a nominal transaction for 100
                PL credit for -100 goods will need a nominal transaction for 100
                SL credit for -100 goods will need a nominal transaction for -100


            A positive header is one where it shows on the purchase or sales ledger as a positive, e.g.
            an invoice.

            A negative header is one where it shows on the purchase or sales ledger as a negative e.g.
            a credit note.

            A debit type header is one where a positive goods value debits a nominal e.g. a PL invoice for goods 100.

            A credit type header is one where a positive goods value credit a nominal e.g. a SL invoice for goods 100.

            `f` is therefore the factor for making sure the nominal transaction value has the correct sign based
            on these considerations.

        """
        to_update, to_delete = super()._edit_nominal_transactions_for_line(
            nom_trans, line, vat_nominal)
        f = self.header_obj.get_nominal_transaction_factor()
        if "t" in nom_trans:
            tran = nom_trans["t"]
            tran.nominal = control_nominal
            tran.value = -1 * f * (line.goods + line.vat)
        if 't' in nom_trans:
            if nom_trans["t"].value:
                to_update.append(nom_trans["t"])
            else:
                to_delete.append(nom_trans["t"])
                line.total_nominal_transaction = None
        return to_update, to_delete

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        control_nominal = self.get_control_nominal(nom_cls, **kwargs)
        kwargs.update({
            "control_nominal": control_nominal
        })
        return super().edit_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)


class CashBookEntryMixin:
    """
    Unlike the other mixins which create nominal and vat transactions, this mixin does not need
    the lines for creating the cash book transaction.  Whether it is a cash book or non cash book
    transaction it only ever creates a single transaction in the cash book.
    """

    def create_cash_book_entry(self, cash_book_tran_cls, **kwargs):
        if self.header_obj.total != 0:
            return cash_book_tran_cls.objects.create(
                module=self.module,
                header=self.header_obj.pk,
                line=1,
                value=self.header_obj.total,
                ref=self.header_obj.ref,
                period=self.header_obj.period,
                date=self.header_obj.date,
                field="t",
                cash_book=self.header_obj.cash_book,
                type=self.header_obj.type
            )

    def edit_cash_book_entry(self, cash_book_tran_cls, **kwargs):
        try:
            cash_book_tran = cash_book_tran_cls.objects.get(
                module=self.module,
                header=self.header_obj.pk,
                line=1
            )
            if self.header_obj.total != 0:
                cash_book_tran.update_details_from_header(self.header_obj)
                cash_book_tran.save()
            else:
                cash_book_tran.delete()
        except cash_book_tran_cls.DoesNotExist:
            if self.header_obj.total != 0:
                self.create_cash_book_entry(cash_book_tran_cls, **kwargs)


class CashBookPaymentTransactionMixin(CashBookEntryMixin, ControlAccountInvoiceTransactionMixin):
    """
    This mixin is for transactions entered via the cash book.  It will create both the nominal
    and cash book entries.

    Whereas CashBookEntryMixin creates the cash book entry for any transaction, either entered via
    the cash book or not, which should update the cash book.
    """

    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        kwargs["control_nominal"] = self.header_obj.cash_book.nominal
        return super().create_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        kwargs["control_nominal"] = self.header_obj.cash_book.nominal
        return super().edit_nominal_transactions(nom_cls, nom_tran_cls, **kwargs)


class ControlAccountPaymentTransactionMixin(BaseNominalTransactionMixin):
    def create_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        if self.header_obj.total != 0:
            f = self.header_obj.get_nominal_transaction_factor()
            control_nominal = self.get_control_nominal(nom_cls, **kwargs)
            nom_trans = []
            # create the bank entry first.  line = 1
            nom_trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,  # header field is PositiveInt field, not Foreign key
                    line="1",
                    nominal=self.header_obj.cash_book.nominal,
                    value=f * self.header_obj.total,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
            # create the control account entry.  line = 2
            nom_trans.append(
                nom_tran_cls(
                    module=self.module,
                    header=self.header_obj.pk,  # header field is PositiveInt field, not Foreign key
                    line="2",
                    nominal=control_nominal,
                    value=-1 * f * self.header_obj.total,
                    ref=self.header_obj.ref,
                    period=self.header_obj.period,
                    date=self.header_obj.date,
                    type=self.header_obj.type,
                    field="t"
                )
            )
            return nom_tran_cls.objects.bulk_create(nom_trans)

    def edit_nominal_transactions(self, nom_cls, nom_tran_cls, **kwargs):
        nom_trans = nom_tran_cls.objects.filter(module=self.module,
                                                header=self.header_obj.pk).order_by("line")
        control_nominal = self.get_control_nominal(nom_cls, **kwargs)
        if nom_trans and self.header_obj.total != 0:
            f = self.header_obj.get_nominal_transaction_factor()
            for tran in nom_trans:
                tran.update_details_from_header(self.header_obj)
            bank_nom_tran, control_nom_tran = nom_trans
            bank_nom_tran.value = f * self.header_obj.total
            bank_nom_tran.nominal = self.header_obj.cash_book.nominal
            control_nom_tran.value = -1 * f * self.header_obj.total
            control_nom_tran.nominal = control_nominal
            nom_tran_cls.objects.bulk_update(nom_trans)
        elif nom_trans and self.header_obj.total == 0:
            nom_tran_cls.objects.filter(
                pk__in=[tran.pk for tran in nom_trans]).delete()
        elif not nom_trans and self.header_obj.total != 0:
            self.create_nominal_transactions(
                nom_cls, nom_tran_cls, control_nominal=control_nominal)

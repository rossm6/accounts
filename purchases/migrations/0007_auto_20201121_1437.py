# Generated by Django 3.1.3 on 2020-11-21 14:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0006_auto_20201121_1241'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='purchaseheader',
            options={'permissions': [('view_transactions_enquiry', 'Can view transactions'), ('view_age_creditors_report', 'Can view aged creditors report'), ('create_brought_forward_invoice_transaction', 'Can create brought forward invoice'), ('create_brought_forward_credit_note_transaction', 'Can create brought forward credit note'), ('create_brought_forward_payment_transaction', 'Can create brought forward payment'), ('create_brought_forward_refund_transaction', 'Can create brought forward refund'), ('create_invoice_transaction', 'Can create invoice'), ('create_credit_note_transaction', 'Can create credit note'), ('create_payment_transaction', 'Can create payment'), ('create_refund_transaction', 'Can create refund'), ('edit_brought_forward_invoice_transaction', 'Can edit brought forward invoice'), ('edit_brought_forward_credit_note_transaction', 'Can edit brought forward credit note'), ('edit_brought_forward_payment_transaction', 'Can edit brought forward payment'), ('edit_brought_forward_refund_transaction', 'Can edit brought forward refund'), ('edit_invoice_transaction', 'Can edit invoice'), ('edit_credit_note_transaction', 'Can edit credit note'), ('edit_payment_transaction', 'Can edit payment'), ('edit_refund_transaction', 'Can edit refund'), ('view_brought_forward_invoice_transaction', 'Can view brought forward invoice'), ('view_brought_forward_credit_note_transaction', 'Can view brought forward credit note'), ('view_brought_forward_payment_transaction', 'Can view brought forward payment'), ('view_brought_forward_refund_transaction', 'Can view brought forward refund'), ('view_invoice_transaction', 'Can view invoice'), ('view_credit_note_transaction', 'Can view credit note'), ('view_payment_transaction', 'Can view payment'), ('view_refund_transaction', 'Can view refund'), ('void_brought_forward_invoice_transaction', 'Can void brought forward invoice'), ('void_brought_forward_credit_note_transaction', 'Can void brought forward credit note'), ('void_brought_forward_payment_transaction', 'Can void brought forward payment'), ('void_brought_forward_refund_transaction', 'Can void brought forward refund'), ('void_invoice_transaction', 'Can void invoice'), ('void_credit_note_transaction', 'Can void credit note'), ('void_payment_transaction', 'Can void payment'), ('void_refund_transaction', 'Can void refund')]},
        ),
    ]

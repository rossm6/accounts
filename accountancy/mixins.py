from accountancy.helpers import DELETED_HISTORY_TYPE, create_historical_records
from accountancy.signals import audit_post_delete


class AuditMixin:
    """

    `simple_history` is the django package used to audit.  It does not provide a way of auditing for bulk
    deletion however.  The solution is easy enough but we must remember to disconnect the simple_history post_delete
    receiver for the model being audited so that it does receive the post_delete signal; 
    otherwise for every item deleted in the bulk delete a post-delete signal is fired which
    creates another audit log !!!

    We then provide our own signal which is fired when delete is called for a model instance but it is not fired
    when we bulk_delete.

    Subclasses should therefore do the following -

        E.g.

            class Contact(Audit, models.Model):
                pass


            register(Contact) # this means simple_history will track the changes
            disconnect_simple_history_receiver_for_post_delete_signal(Contact)
            audit_post_delete.connect(Contact.post_delete, sender=Contact, dispatch_uid=uuid4())


    Then we can safely do -

        bulk_delete_with_history([contact_instances])

    """
    
    @classmethod
    def post_delete(cls, sender, instance, **kwargs):
        return create_historical_records([instance], instance._meta.model, DELETED_HISTORY_TYPE)

    def delete(self):
        audit_post_delete.send(sender=self._meta.model, instance=self)
        super().delete()

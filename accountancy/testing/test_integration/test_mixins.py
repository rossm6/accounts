from accountancy.helpers import bulk_delete_with_history
from contacts.models import Contact
from django.test import TestCase


class AuditMixinTest(TestCase):

    def test_instance_deleted(self):
        c = Contact(
            code="1",
            name="contact1",
            email="doris@hotmail.com"
        )
        c.save()
        c.delete()
        self.assertEqual(
            len(
                Contact.history.all()
            ),
            2 # created + deleted audits
        )

    def test_queryset_deleted(self):
        c = Contact(
            code="1",
            name="contact1",
            email="doris@hotmail.com"
        )
        c.save()
        Contact.objects.all().delete()
        self.assertEqual(
            len(
                Contact.history.all()
            ),
            1 # created audit only
            # deleted audit is not created
            # use bulk_delete_with_history for deleted audits
        )

    # USE THIS LATER FOR TESTING BULK_DELETE_WITH_HISTORY
    # def test_bulk_deleted(self):
    #     contacts = []
    #     for i in range(100):
    #         contacts.append(
    #             Contact(
    #                 code=i,
    #                 name="contact" + str(i),
    #                 email="doris@hotmail.com"
    #             )
    #         )
    #     Contact.objects.bulk_create(contacts)
    #     contacts = Contact.objects.all()
    #     self.assertEqual(
    #         len(contacts),
    #         100
    #     )
    #     history = Contact.history.all()
    #     self.assertEqual(
    #         len(history),
    #         0 # because audited_bulk_create not used
    #     )
    #     bulk_delete_with_history(contacts, Contact)
    #     self.assertEqual(
    #         len(Contact.objects.all()),
    #         0
    #     )
    #     history = Contact.history.all()
    #     self.assertEqual(
    #         len(history),
    #         100  # a history record for object deleted
    #     )
    #     # this proves that the post_delete signal was not received
    #     # by the simple_history post_delete receiver

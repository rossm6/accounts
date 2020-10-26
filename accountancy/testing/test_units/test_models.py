import mock
from accountancy.models import NonAuditQuerySet, Transaction
from django.test import TestCase


class NonAuditQuerySetTest(TestCase):

    def test_bulk_line_update(self):
        pass
        # # https://www.integralist.co.uk/posts/mocking-in-python/#mock-instance-method
        # with mock.patch('accountancy.models.NonAuditQuerySet.bulk_update') as mock_method:
        #     o = mock.Mock()
        #     o = NonAuditQuerySet.as_manager()
        #     o.model = mock.Mock()
        #     o.model.fields_to_update = mock.Mock()
        #     o.model.fields_to_update.return_value = []
        #     o.bulk_line_update([])
        #     mock_method.assert_called_once()
        #     call = next(iter(mock_method.call_args_list))
        #     args, kwargs = call
        #     objs, fields_to_update = args
        #     assert len(kwargs) == 1
        #     assert objs == []
        #     assert fields_to_update == []
        #     batch_size = kwargs["batch_size"]
        #     assert batch_size is None


class AuditQuerySetTest(TestCase):
    pass


class TransactionTest(TestCase):

    def test_without_header(self):
        class TransactionNew(Transaction):
            module = "PL"

        self.assertRaises(ValueError, TransactionNew)

    def test_without_module(self):
        try:
            class TransactionNew(Transaction):
                pass
            self.fail("Should not allow without module")
        except ValueError:
            pass

    def test_vat_type_on_header(self):
        raise NotImplementedError

    def test_vat_type_on_transaction_class(self):
        raise NotImplementedError

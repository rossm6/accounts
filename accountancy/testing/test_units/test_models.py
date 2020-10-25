from django.test import TestCase
import mock

from accountancy.models import NonAuditQuerySet

class NonAuditQuerySetTest(TestCase):

    def test_bulk_line_update(self):
        # https://www.integralist.co.uk/posts/mocking-in-python/#mock-instance-method
        with mock.patch('accountancy.models.NonAuditQuerySet.bulk_update') as mock_method:
            o = mock.Mock()
            o = NonAuditQuerySet.as_manager()
            o.model = mock.Mock()
            o.model.fields_to_update = mock.Mock()
            o.model.fields_to_update.return_value = []
            o.bulk_line_update([])
            mock_method.assert_called_once()
            call = next(iter(mock_method.call_args_list))
            args, kwargs = call
            objs, fields_to_update = args
            assert len(kwargs) == 1
            assert objs == []
            assert fields_to_update == []
            batch_size = kwargs["batch_size"]
            assert batch_size is None


class AuditQuerySetTest(TestCase):
    pass



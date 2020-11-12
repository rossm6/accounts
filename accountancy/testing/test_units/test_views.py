from datetime import date

import mock
from accountancy.views import JQueryDataTableMixin, get_value
from deepdiff import DeepDiff
from django.test import TestCase
from nominals.models import Nominal


class JQueryDataTableMixinPaginateObjectsTests(TestCase):

    def test_paginate_objects_page_1(self):
        objs = []
        for i in range(50):
            o = {"i": i}
            objs.append(o)

        mock_self = mock.Mock()
        mock_self.request.GET = {"start": 0, "length": 25}
        paginator_obj, page_obj = JQueryDataTableMixin.paginate_objects(
            mock_self, objs)
        self.assertEqual(
            paginator_obj.object_list,
            objs
        )
        self.assertEqual(
            paginator_obj.per_page,
            25
        )
        self.assertEqual(
            paginator_obj.count,
            50
        )
        self.assertEqual(
            paginator_obj.num_pages,
            2
        )
        self.assertEqual(
            page_obj.object_list,
            objs[:25]
        )
        self.assertEqual(
            page_obj.number,
            1
        )
        self.assertEqual(
            page_obj.has_other_pages(),
            True
        )

    def test_paginate_objects_page_2(self):
        objs = []
        for i in range(50):
            o = {"i": i}
            objs.append(o)
        mock_self = mock.Mock()
        mock_self.request.GET = {"start": 25, "length": 25}
        paginator_obj, page_obj = JQueryDataTableMixin.paginate_objects(
            mock_self, objs)
        self.assertEqual(
            paginator_obj.object_list,
            objs
        )
        self.assertEqual(
            paginator_obj.per_page,
            25
        )
        self.assertEqual(
            paginator_obj.count,
            50
        )
        self.assertEqual(
            paginator_obj.num_pages,
            2
        )
        self.assertEqual(
            page_obj.object_list,
            objs[25:]
        )
        self.assertEqual(
            page_obj.number,
            2
        )
        self.assertEqual(
            page_obj.has_other_pages(),
            True
        )

    def test_paginate_objects_page_3_is_blank(self):
        objs = []
        for i in range(50):
            o = {"i": i}
            objs.append(o)
        mock_self = mock.Mock()
        mock_self.request.GET = {"start": 51, "length": 25}
        paginator_obj, page_obj = JQueryDataTableMixin.paginate_objects(
            mock_self, objs)
        self.assertEqual(
            paginator_obj.object_list,
            objs
        )
        self.assertEqual(
            paginator_obj.per_page,
            25
        )
        self.assertEqual(
            paginator_obj.count,
            50
        )
        self.assertEqual(
            paginator_obj.num_pages,
            2
        )
        self.assertEqual(
            page_obj.object_list,
            objs[25:]
        )
        self.assertEqual(
            page_obj.number,
            2
        )
        self.assertEqual(
            page_obj.has_other_pages(),
            True
        )


class JQueryDataTableMixinOrderByTests(TestCase):

    def test_asc(self):
        d = {
            'draw': '3',
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}},
                1: {'data': 'supplier__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                3: {'data': 'period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            },
            'order': {
                0: {'column': '1', 'dir': 'asc'}
            },
            'start': '0',
            'length': '10',
            'search': {
                'value': '',
                'regex': 'false'
            },
            'supplier': '',
            'reference': '',
            'total': '',
            'period': '',
            'search_within': 'any',
            'start_date': '',
            'end_date': '',
            'use_adv_search': 'False'
        }
        mock_self = mock.Mock()
        mock_self.request.GET.urlencode.return_value = ""
        with mock.patch("accountancy.views.parser.parse") as mocked_parse:
            mocked_parse.return_value = d
            ordering = JQueryDataTableMixin.order_by(mock_self)
            self.assertEqual(
                len(ordering),
                1
            )
            self.assertEqual(
                ordering[0],
                "supplier__name"
            )

    def test_desc(self):
        d = {
            'draw': '3',
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}},
                1: {'data': 'supplier__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                3: {'data': 'period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            },
            'order': {
                0: {'column': '1', 'dir': 'desc'}
            },
            'start': '0',
            'length': '10',
            'search': {
                'value': '',
                'regex': 'false'
            },
            'supplier': '',
            'reference': '',
            'total': '',
            'period': '',
            'search_within': 'any',
            'start_date': '',
            'end_date': '',
            'use_adv_search': 'False'
        }
        mock_self = mock.Mock()
        mock_self.request.GET.urlencode.return_value = ""
        with mock.patch("accountancy.views.parser.parse") as mocked_parse:
            mocked_parse.return_value = d
            ordering = JQueryDataTableMixin.order_by(mock_self)
            self.assertEqual(
                len(ordering),
                1
            )
            self.assertEqual(
                ordering[0],
                "-supplier__name"
            )

    def test_one_asc_another_desc(self):
        d = {
            'draw': '3',
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}},
                1: {'data': 'supplier__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                3: {'data': 'period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            },
            'order': {
                0: {'column': '1', 'dir': 'desc'},
                1: {'column': '2', 'dir': 'asc'}
            },
            'start': '0',
            'length': '10',
            'search': {
                'value': '',
                'regex': 'false'
            },
            'supplier': '',
            'reference': '',
            'total': '',
            'period': '',
            'search_within': 'any',
            'start_date': '',
            'end_date': '',
            'use_adv_search': 'False'
        }
        mock_self = mock.Mock()
        mock_self.request.GET.urlencode.return_value = ""
        with mock.patch("accountancy.views.parser.parse") as mocked_parse:
            mocked_parse.return_value = d
            ordering = JQueryDataTableMixin.order_by(mock_self)
            self.assertEqual(
                len(ordering),
                2
            )
            self.assertEqual(
                ordering[0],
                "-supplier__name"
            )
            self.assertEqual(
                ordering[1],
                "ref"
            )

    def test_invalid_column_index_not_integer(self):
        d = {
            'draw': '3',
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}},
                1: {'data': 'supplier__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                3: {'data': 'period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            },
            'order': {
                0: {'column': 'p', 'dir': 'desc'},
                1: {'column': '2', 'dir': 'asc'}
            },
            'start': '0',
            'length': '10',
            'search': {
                'value': '',
                'regex': 'false'
            },
            'supplier': '',
            'reference': '',
            'total': '',
            'period': '',
            'search_within': 'any',
            'start_date': '',
            'end_date': '',
            'use_adv_search': 'False'
        }
        mock_self = mock.Mock()
        mock_self.request.GET.urlencode.return_value = ""
        with mock.patch("accountancy.views.parser.parse") as mocked_parse:
            mocked_parse.return_value = d
            ordering = JQueryDataTableMixin.order_by(mock_self)
            self.assertEqual(
                len(ordering),
                0
            )

    def test_invalid_column_index(self):
        d = {
            'draw': '3',
            'columns': {
                0: {'data': '', 'name': '', 'searchable': 'false', 'orderable': 'false', 'search': {'value': '', 'regex': 'false'}},
                1: {'data': 'supplier__name', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                2: {'data': 'ref', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                3: {'data': 'period', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                4: {'data': 'date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                5: {'data': 'due_date', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                6: {'data': 'total', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                7: {'data': 'paid', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}},
                8: {'data': 'due', 'name': '', 'searchable': 'true', 'orderable': 'true', 'search': {'value': '', 'regex': 'false'}}
            },
            'order': {
                0: {'column': '11', 'dir': 'desc'},
                1: {'column': '2', 'dir': 'asc'}
            },
            'start': '0',
            'length': '10',
            'search': {
                'value': '',
                'regex': 'false'
            },
            'supplier': '',
            'reference': '',
            'total': '',
            'period': '',
            'search_within': 'any',
            'start_date': '',
            'end_date': '',
            'use_adv_search': 'False'
        }
        mock_self = mock.Mock()
        mock_self.request.GET.urlencode.return_value = ""
        with mock.patch("accountancy.views.parser.parse") as mocked_parse:
            mocked_parse.return_value = d
            ordering = JQueryDataTableMixin.order_by(mock_self)
            self.assertEqual(
                len(ordering),
                0
            )


class GetValueTests(TestCase):

    def test_obj_is_model_instance(self):
        n = Nominal(name="n")
        self.assertEqual(
            get_value(n, "name"),
            "n"
        )

    def test_obj_is_dict(self):
        n = {"name": "n"}
        self.assertEqual(
            get_value(n, "name"),
            "n"
        )


class JQueryDataTableMixinOrderObjectsTests(TestCase):
    """
    sort_multiple is not yet tested which this relies on.  It just taken from SO though so testing 
    is a low priority (very high rated answer).
    """

    def test(self):
        with mock.patch("accountancy.views.JQueryDataTableMixin.order_by") as mocked_order_by, \
                mock.patch("accountancy.views.get_value") as mocked_get_value, \
                mock.patch("accountancy.views.sort_multiple") as mocked_sort_multiple:

            mocked_order_by.return_value = ["total", "-ref"]
            mocked_get_value.return_value = "a"
            j = JQueryDataTableMixin()
            j.order_objects([mock.Mock()])
            args, kwargs = mocked_sort_multiple.call_args_list[0]
            self.assertEqual(
                args[1][1],
                False
            )
            self.assertEqual(
                args[2][1],
                True
            )


class JQueryDataTableMixinTests(TestCase):

    """
    test apply_filter method
    """

    @mock.patch("accountancy.views.parser.parse")
    def test_apply_filter_without_search_value(self, mocked_parse):
        q = mock.Mock()
        j = JQueryDataTableMixin()
        j.request = mock.Mock()
        self.assertEqual(
            j.apply_filter(q),
            q
        )

    @mock.patch("accountancy.views.parser.parse")
    def test_apply_filter_without_searchable_fields(self, mocked_parse):
        mocked_parse.return_value = {
            "search": {
                "value": "some value"
            }
        }
        q = mock.Mock()
        j = JQueryDataTableMixin()
        j.request = mock.Mock()
        new_queryset = j.apply_filter(q)
        self.assertEqual(
            j.apply_filter(q),
            q
        )

    @mock.patch("accountancy.views.get_trig_vectors_for_different_inputs")
    @mock.patch("accountancy.views.parser.parse")
    def test_apply_filter_with_searchable_fields(self, mocked_parse, mocked_get_inputs):
        mocked_get_inputs.return_value = mock.Mock()
        mocked_parse.return_value = {
            "search": {
                "value": "some value"
            }
        }
        q = mock.Mock()
        j = JQueryDataTableMixin()
        j.searchable_fields = ["some field"]
        j.request = mock.Mock()
        new_queryset = j.apply_filter(q)
        self.assertEqual(
            new_queryset._extract_mock_name(),
            "mock.annotate().filter()"
        )

    """
    test get_row method
    """

    def test_get_rows(self):
        j = JQueryDataTableMixin()
        j.columns = ["some_column"]
        o = mock.Mock()
        o.some_column = "some_column_value"
        row = j.get_row(o)
        self.assertEqual(
            row,
            {
                'some_column': 'some_column_value'
            }
        )

    """
    test get_queryset method
    """

    def test_get_queryset(self):
        j = JQueryDataTableMixin()
        with mock.patch.object(j, "get_model") as mock_model:
            self.assertEqual(
                j.get_queryset()._extract_mock_name(),
                "get_model().objects.all()"
            )

    """
    test get_table_data method
    """

    def test_get_table_data_with_empty_object_list(self):
        pass

    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.get_row_href")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.get_row_identifier")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.get_row")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.paginate_objects")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.order_by")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.apply_filter")
    @mock.patch("accountancy.testing.test_units.test_views.JQueryDataTableMixin.get_queryset")
    def test_get_table_data_with_object_list(
        self,
        mocked_get_queryset,
        mocked_apply_filter,
        mocked_order_by,
        mocked_paginate_objects,
        mocked_get_row,
        mocked_get_row_identifier,
        mocked_get_row_href
    ):
        j = JQueryDataTableMixin()
        mocked_order_by.return_value = []
        count_queryset = mock.Mock()
        count_queryset.return_value = 1
        mock_queryset = mock.Mock()
        mock_queryset.return_value = mock_queryset
        mock_queryset.count = count_queryset
        mock_queryset.all = mock_queryset
        mock_queryset.order_by = mock_queryset
        mocked_apply_filter.return_value = mock_queryset
        mocked_get_queryset.return_value = mocked_apply_filter
        paginator_object = mock.Mock()
        paginator_object.count = 2
        page_object = mock.Mock()
        page_object.object_list = [1, 2, 3]
        mocked_paginate_objects.return_value = paginator_object, page_object
        mocked_get_row.return_value = {}
        mocked_get_row_identifier.return_value = 3
        mocked_get_row_href.return_value = ""
        j.request = mock.Mock()
        j.request.GET.get = mock.Mock()
        j.request.GET.get.return_value = 4
        result = j.get_table_data()
        expected = {
            "draw": 4,
            "recordsTotal": 1,
            "recordsFiltered": 2,
            "data": [
                {"DT_RowData": {
                    "pk": 3,
                    "href": ""
                }},
                {"DT_RowData": {
                    "pk": 3,
                    "href": ""
                }},
                {"DT_RowData": {
                    "pk": 3,
                    "href": ""
                }}
            ]
        }
        self.assertEqual(
            DeepDiff(expected, result),
            {}
        )


class CustomFilterJQueryDataTableMixinTests(TestCase):

    """
    test get_table_data method
    """

    def test_get_table_data_without_adv_search_form(self):
        pass

    def test_get_table_data_with_adv_search_form(self):
        pass

    """
    test get_filter_form_kwargs method
    """

    def test_get_filter_form_kwargs_with_unbound_form(self):
        pass

    def test_get_filter_form_kwargs_with_bound_form(self):
        pass

    """
    test get_filter_form method
    """

    def test_get_filter_form(self):
        pass

    """
    test apply_filter method
    """

    def test_apply_filter_when_form_is_valid(self):
        pass

    def test_apply_filter_when_form_is_invalid(self):
        pass


class BaseTransactionsListTests(TestCase):

    """
    This method needs a note has it is a bit confusing
    """

    def test_get_list_of_search_values_for_model_attrs(self):
        pass

    """
    test load_page method
    """

    def test_load_page(self):
        pass

    """
    test get_row
    """

    def test_get_row(self):
        pass

    """
    test form_form_valid method
    """

    def test_filter_form_valid(self):
        pass

    """
    test get_row_identifier method
    """

    def test_get_row_identifier(self):
        pass

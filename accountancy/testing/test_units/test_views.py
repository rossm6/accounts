from datetime import date

import mock
from accountancy.views import get_value, jQueryDataTableMixin
from django.test import TestCase
from nominals.models import Nominal


class jQueryDataTableMixinPaginateObjectsTests(TestCase):

    def test_paginate_objects_page_1(self):
        objs = []
        for i in range(50):
            o = {"i": i}
            objs.append(o)

        mock_self = mock.Mock()
        mock_self.request.GET = {"start": 0, "length": 25}
        paginator_obj, page_obj = jQueryDataTableMixin.paginate_objects(
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
        paginator_obj, page_obj = jQueryDataTableMixin.paginate_objects(
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
        paginator_obj, page_obj = jQueryDataTableMixin.paginate_objects(
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


class jQueryDataTableMixinOrderByTests(TestCase):

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
            ordering = jQueryDataTableMixin.order_by(mock_self)
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
            ordering = jQueryDataTableMixin.order_by(mock_self)
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
            ordering = jQueryDataTableMixin.order_by(mock_self)
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
            ordering = jQueryDataTableMixin.order_by(mock_self)
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
            ordering = jQueryDataTableMixin.order_by(mock_self)
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


class jQueryDataTableMixinOrderObjectsTests(TestCase):
    """
    sort_multiple is not yet tested which this relies on.  It just taken from SO though so testing 
    is a low priority (very high rated answer).
    """
    def test(self):
        with mock.patch("accountancy.views.jQueryDataTableMixin.order_by") as mocked_order_by, \
            mock.patch("accountancy.views.get_value") as mocked_get_value, \
            mock.patch("accountancy.views.sort_multiple") as mocked_sort_multiple:

            mocked_order_by.return_value = ["total", "-ref"]
            mocked_get_value.return_value = "a"
            j = jQueryDataTableMixin()
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
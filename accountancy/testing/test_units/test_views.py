from datetime import date

import mock
from accountancy.views import (BaseTransactionsList,
                               CustomFilterJQueryDataTableMixin,
                               JQueryDataTableMixin, RESTBaseTransactionMixin,
                               get_value)
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
        j.model = mock.Mock()
        q = j.get_queryset()
        self.assertEqual(
            q._extract_mock_name(),
            "mock.objects.all()"
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

    @mock.patch("accountancy.views.render_crispy_form")
    @mock.patch("accountancy.views.csrf")
    @mock.patch("builtins.super")
    @mock.patch("accountancy.views.CustomFilterJQueryDataTableMixin.get_filter_form")
    def test_get_table_data_without_adv_search_form(
            self,
            mock_get_filter_form,
            mock_super,
            mock_csrf,
            mock_render_crispy_form):
        j = CustomFilterJQueryDataTableMixin()
        j.request = mock.Mock()
        j.request.GET.get = mock.Mock()
        j.request.GET.get.return_value = False
        mock_get_filter_form.return_value = "form_object"
        mock_super().get_table_data.return_value = {}
        mock_csrf.return_value = {"csrf": "something"}
        mock_render_crispy_form.return_value = "<form></form>"
        table_data = j.get_table_data()

        args, kwargs = mock_get_filter_form.call_args_list[0]
        self.assertEqual(
            len(args),
            0
        )
        self.assertEqual(
            len(kwargs),
            0
        )
        self.assertEqual(
            table_data,
            {
                "form": "<form></form>"
            }
        )

    @mock.patch("accountancy.views.render_crispy_form")
    @mock.patch("accountancy.views.csrf")
    @mock.patch("builtins.super")
    @mock.patch("accountancy.views.CustomFilterJQueryDataTableMixin.get_filter_form")
    def test_get_table_data_with_adv_search_form(
            self,
            mock_get_filter_form,
            mock_super,
            mock_csrf,
            mock_render_crispy_form):
        j = CustomFilterJQueryDataTableMixin()
        j.request = mock.Mock()
        j.request.GET.get = mock.Mock()
        j.request.GET.get.return_value = True
        mock_get_filter_form.return_value = "form_object"
        mock_super().get_table_data.return_value = {}
        mock_csrf.return_value = {"csrf": "something"}
        mock_render_crispy_form.return_value = "<form></form>"
        table_data = j.get_table_data()

        args, kwargs = mock_get_filter_form.call_args_list[0]
        self.assertEqual(
            len(args),
            0
        )
        self.assertEqual(
            len(kwargs),
            1
        )
        self.assertEqual(
            kwargs,
            {
                "bind_form": True
            }
        )
        self.assertEqual(
            table_data,
            {
                "form": "<form></form>"
            }
        )

    """
    test get_filter_form_kwargs method
    """

    def test_get_filter_form_kwargs_with_unbound_form(self):
        j = CustomFilterJQueryDataTableMixin()
        form_kwargs = j.get_filter_form_kwargs()
        self.assertEqual(
            form_kwargs,
            {}
        )

    def test_get_filter_form_kwargs_with_bound_form(self):
        j = CustomFilterJQueryDataTableMixin()
        j.request = mock.Mock()
        j.request.GET = {"some_field": "some_value"}
        form_kwargs = j.get_filter_form_kwargs(bind_form=True)
        self.assertEqual(
            form_kwargs,
            {
                "data": {"some_field": "some_value"}
            }
        )

    """
    test get_filter_form method
    """

    @mock.patch("accountancy.views.CustomFilterJQueryDataTableMixin.get_filter_form_kwargs")
    def test_get_filter_form(self, mock_get_filter_form_kwargs):
        mock_get_filter_form_kwargs.return_value = {
            "data": {
                "some_field": "some_value"
            }
        }
        j = CustomFilterJQueryDataTableMixin()
        j.filter_form_class = mock.Mock
        form_instance = j.get_filter_form()
        self.assertEqual(
            form_instance.data,
            {
                "some_field": "some_value"
            }
        )

    """
    test apply_filter method
    """

    @mock.patch("accountancy.views.CustomFilterJQueryDataTableMixin.filter_form_valid")
    def test_apply_filter_when_form_is_valid(self, mock_filter_form_valid):
        j = CustomFilterJQueryDataTableMixin()
        mock_form = mock.Mock()
        mock_form.is_valid.return_value = True
        kwargs = {"form": mock_form}
        queryset = mock.Mock()
        mock_filter_form_valid.return_value = queryset
        result = j.apply_filter(queryset, **kwargs)
        args, kwargs = mock_filter_form_valid.call_args_list[0]
        self.assertEqual(
            len(args),
            2
        )
        self.assertEqual(
            args[0],
            queryset
        )
        self.assertEqual(
            args[1],
            mock_form
        )
        self.assertEqual(
            queryset,
            result
        )

    @mock.patch("accountancy.views.CustomFilterJQueryDataTableMixin.filter_form_invalid")
    def test_apply_filter_when_form_is_invalid(self, mock_filter_form_invalid):
        j = CustomFilterJQueryDataTableMixin()
        mock_form = mock.Mock()
        mock_form.is_valid.return_value = False
        kwargs = {"form": mock_form}
        queryset = mock.Mock()
        mock_filter_form_invalid.return_value = queryset
        result = j.apply_filter(queryset, **kwargs)
        args, kwargs = mock_filter_form_invalid.call_args_list[0]
        self.assertEqual(
            len(args),
            2
        )
        self.assertEqual(
            args[0],
            queryset
        )
        self.assertEqual(
            args[1],
            mock_form
        )
        self.assertEqual(
            queryset,
            result
        )


class BaseTransactionsListTests(TestCase):

    """
    This method needs a note as it is a bit confusing
    """

    def test_get_list_of_search_values_for_model_attrs_without_search_values_defined(self):
        b = BaseTransactionsList()
        form_cleaned_data = {
            "some_form_field": "some_value"
        }
        search = b.get_list_of_search_values_for_model_attrs(form_cleaned_data)
        self.assertEqual(
            len(search),
            0
        )

    def test_get_list_of_search_values_for_model_attrs(self):
        b = BaseTransactionsList()
        b.form_field_to_searchable_model_attr = {
            "some_form_field": "some_model_attr"
        }
        form_cleaned_data = {
            "some_form_field": "some_value"
        }
        search = b.get_list_of_search_values_for_model_attrs(form_cleaned_data)
        self.assertEqual(
            len(search),
            1
        )
        model_attr, form_value = search[0]
        self.assertEqual(
            model_attr,
            "some_model_attr"
        )
        self.assertEqual(
            form_value,
            "some_value"
        )

    """
    test load_page method
    """

    def test_load_page(self):
        b = BaseTransactionsList()
        b.fields = [
            ("model_field", "model_field_in_ui")
        ]
        context_data = b.load_page()
        self.assertEqual(
            context_data["columns"],
            ["model_field"]
        )
        self.assertEqual(
            context_data["column_labels"],
            ["model_field_in_ui"]
        )

    """
    test get_row
    """

    def test_get_row_without_column_transformer(self):
        b = BaseTransactionsList()
        o = {"model_attr": "model_attr_value"}
        obj = b.get_row(o)
        self.assertEqual(
            obj,
            o
        )

    def test_get_row_with_column_transformer(self):
        b = BaseTransactionsList()
        b.column_transformers = {
            "model_attr": lambda v: "duh"
        }
        o = {"model_attr": "model_attr_value"}
        obj = b.get_row(o)
        self.assertEqual(
            obj,
            {
                "model_attr":
                "duh"
            }
        )

    """
    test form_form_valid method
    """

    def test_filter_form_valid(self):
        b = BaseTransactionsList()
        queryset = mock.Mock()
        cleaned_data = mock.Mock()
        b.apply_advanced_search = mock.Mock()
        b.apply_advanced_search(queryset, cleaned_data)
        args, kwargs = b.apply_advanced_search.call_args_list[0]
        self.assertEqual(
            len(args),
            2
        )
        self.assertEqual(
            args[0],
            queryset
        )
        self.assertEqual(
            args[1],
            cleaned_data
        )

    """
    test get_row_identifier method
    """

    def test_get_row_identifier_default(self):
        b = BaseTransactionsList()
        row = {"id": "duh"}
        identifier = b.get_row_identifier(row)
        self.assertEqual(
            identifier,
            "duh"
        )

    def test_get_row_identifier_defined(self):
        b = BaseTransactionsList()
        b.row_identifier = "doris"
        row = {"doris": "derek"}
        identifier = b.get_row_identifier(row)
        self.assertEqual(
            identifier,
            "derek"
        )


class RESTBaseTransactionMixinTests(TestCase):

    """
    test get_transaction_type_object method
    """

    def test_get_transaction_type_object_without_attribute(self):
        pass

    def test_get_transaction_type_object_with_attribute(self):
        pass

    """
    test 
    """

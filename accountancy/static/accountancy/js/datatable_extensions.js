(function(root, module){
    root.dataTable_extensions = module();
})(window, function(){

    // Buttons

    // Search button - triggers the advanced search form to show
    $.fn.dataTable.ext.buttons.show_search_form = {
        text: 'Search',
        className: 'btn button search-btn-trigger f-s-100',
        action: function (e, dt, node, config) {
            $(".adv-search-form").toggleClass("d-none");
            node.hide();
        },
        init: function (api, node, config) {
            $(node).removeClass("dt-button");
            // https://stackoverflow.com/questions/45299188/how-can-i-remove-default-button-class-of-a-datatables-button
        }
    };


    // Batch Payment - click on this to pay / match the rows you have ticked
    //$.fn.dataTable.ext.buttons.batch_payment = {
        //name: 'batch_payment',
        //text: 'Batch Payment',
        //className: 'btn button batch-payment-btn-trigger',
        //action: function (e, dt, node, config) {
            //var form = $("form.table_form");
            //form.attr("action", batch_payment_url);
            //form.submit();
        //},
        //init: function (api, node, config) {
            //$(node).removeClass("dt-button");
            // https://stackoverflow.com/questions/45299188/how-can-i-remove-default-button-class-of-a-datatables-button
        //}
    //};


    // Pagination widgets can be used multiple times in jQuery datatables
    // but the catch is it must indeed be the exact same widget
    // Our transaction table needed two DIFFERENT widgets
    // So, in addition to the built in widget, we created this -
    // AltPagination

    $.fn.dataTable.AltPagination = function (settings) {

        var instance = settings.oInstance;
        var table = instance.api();

        var new_buttons = "";
        var first = "<span class='pagination-numbers-ui pagination-numbers-ui-button' data-value='first'>First</span>";
        var previous = "<span class='pagination-numbers-ui pagination-numbers-ui-button' data-value='previous'>Previous</span>";
        var next = "<span class='pagination-numbers-ui pagination-numbers-ui-button' data-value='next'>Next</span>";
        var end = "<span class='pagination-numbers-ui pagination-numbers-ui-button' data-value='last'>End</span>";

        var info = table.page.info();

        if (info.page) {
            new_buttons += first;
            new_buttons += previous;
        }

        var lower = info.page - 4;
        var higher = info.page + 4;
        var pages = [];

        for (var i = lower; i <= higher; i++) {
            if (0 <= i && i <= info.pages - 1) {
                pages.push(i);
            }
        }

        // current page must be in pages
        if (pages.length > 4) {
            var current_page_index = pages.indexOf(info.page);
            if (current_page_index > 2) {
                pages = pages.slice(current_page_index - 2, current_page_index + 1);
            } else {
                pages = pages.slice(0, 4);
            }
        }

        if (pages.length > 1) {
            for (var i = 0; i < pages.length; i++) {
                // pages contains page numbers
                // but the label is plus 1
                // because page 1 is page 0
                new_buttons += "<span class='pagination-numbers-ui pagination-numbers-ui-number'";
                if (i == info.page) {
                    new_buttons += " data-selected ";
                }
                new_buttons += " data-value='" + pages[i] + "' "
                new_buttons += ">";
                new_buttons += (pages[i] + 1) + "</span>";
            }
        } else {
            new_buttons += "";
        }


        if (info.page != info.pages - 1) {
            new_buttons += next;
            new_buttons += end;
        }

        new_buttons = $(new_buttons);
        new_buttons = $("<div class='pagination-numbers-ui-wrapper'>").append(new_buttons);
        new_buttons = new_buttons.get(0);

        return new_buttons;

    };


    $.fn.dataTable.ext.feature.push({
        fnInit: function (settings) {
            var altPagination = new $.fn.dataTable.AltPagination(settings);
            return altPagination;
        },
        cFeature: 'P'
    });

    function add_alt_pagination_events(settings) {
        var instance = settings.oInstance;
        var table = instance.api();

        $(".pagination-numbers-ui").on("click", function () {
            var value = $(this).attr("data-value");
            var non_page_values = ["first", "previous", "next", "last"];
            if (non_page_values.indexOf(value) == -1) {
                value = +value;
                // see api - https://datatables.net/reference/api/page()
                // if you don't do this you will get an error
                // and it won't work
            }
            table.page(value).draw("page");
        });

    }

    // A standalone function
    function add_result_count_to_select_pagination_widget(settings) {
        var instance = settings.oInstance;
        var api = instance.api();
        var result_set_count = api.page.info().recordsTotal;
        $(".result_set_count").text("(" + result_set_count + " total items)");
    }

    return {
        add_alt_pagination_events: add_alt_pagination_events,
        add_result_count_to_select_pagination_widget: add_result_count_to_select_pagination_widget
    }

});
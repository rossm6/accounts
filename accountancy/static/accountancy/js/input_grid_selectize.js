(function (root, module) {
    root.input_grid_selectize = module();
})(window, function () {

    // vat selectize
    function vat(select_menu) {
        var $select = $(select_menu);
        var load_url = $select.attr("data-url");
        return $select.selectize({
            openOnFocus: true,
            valueField: 'id',
            labelField: 'code',
            searchField: 'code',
            dropdownParent: 'body',
            render: {
                option: function (item, escape) {
                    var label = item.code;
                    var rate = item.rate;
                    return '<div class="p-1" data-rate="' + rate + '">' + escape(label) + '</div>';
                }
            },
            load: function (query, callback) {
                $.ajax({
                    url: load_url,
                    type: "GET",
                    dataType: 'json',
                    data: {
                        q: query,
                        page_limit: 10 
                    },
                    error: function (qXHR, textStatus, errorThrown) {
                        console.log("Error occured");
                        console.log("Logging...");
                        console.log("qXHR", qXHR);
                        console.log("textStatus", textStatus);
                        console.log("errorThrown", errorThrown);
                        console.log("Logging complete");
                    },
                    success: function (res, textStatus, jqXHR) {
                        callback(res.data);
                    }
                });
            }
        });
    }


    function nominal (select_menu) {
        // based on - https://stackoverflow.com/a/50959514
        // difference is we load from a remote source

        // notes -
        // ordering by opt group is either of two options.
        // 1. go on the order groups were added 
        // 2. the order of rank i.e how many options in each group i think

        // I therefore rely on the server returning the data in the option group order.
        // There is no need to specify the $order in the optionGroup because of the two rules above (I don't understand the meaning of $order)

        // Similarly, with ordering of options, it seems you must specify the $score order for it to work
        var $select = $(select_menu);
        var load_url = $select.attr("data-url");
        return $select.selectize({
            openOnFocus: true,
            valueField: 'opt_value',
            labelField: 'opt_label',
            searchField: 'opt_label', // was `name` but this means the dropdown doesn't appear as you type
            optgroupField: 'group_label',
            dropdownParent: 'body',
            lockOptgroupOrder: true,
            sortField: [
                {
                    field: 'opt_value',
                    direction: 'asc'
                },
                {
                    field: '$score'
                }
            ],
            load: function (query, callback) {
                var self = this;
                $.ajax({
                    url: load_url,
                    type: "GET",
                    dataType: 'json',
                    data: {
                        q: query,
                        page_limit: 10 
                    },
                    error: function (qXHR, textStatus, errorThrown) {
                        console.log("Error occured");
                        console.log("Logging...");
                        console.log("qXHR", qXHR);
                        console.log("textStatus", textStatus);
                        console.log("errorThrown", errorThrown);
                        console.log("Logging complete");
                    },
                    success: function (res, textStatus, jqXHR) {
                        self.clearOptionGroups();
                        self.clearOptions();
                        $.each(res.data, function(index, value) {
                            self.addOptionGroup(value["group_label"], { label: value["group_label"], value: value["group_label"]});
                          });
                        callback(res.data);
                    },
                });
            },
        });        
    }


    return {
        nominal: nominal,
        vat: vat
    }

});
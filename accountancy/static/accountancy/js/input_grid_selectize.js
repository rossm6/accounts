(function (root, module) {
    root.input_grid_selectize = module();
})(window, function () {

    /*

        Selectize is an awkward plugin I find.  Take note of the following -

        1. HTML5 data attributes are wiped from the option elements.  The workaround is
           is in the `onInitialize` method.

        2. The dropdown was not showing straight away when I was searching because the
           `search` option was not well defined.  It should be one of the keys in the
            the ajax response i believe.

        3. So that the dropdown is visible we need to set `dropdownParent` to `body`.

        4. I needed to set the option groups based on the ajax response.  Again this
           was a nightmare.  Use the nominal selectize config for help with this.

        5. Likewise sorting the groups was tricky.  Refer to the nominal config
           for help.

        Select2 might be a better choice.

    */


    // vat selectize
    function vat(select_menu) {
        var $select = $(select_menu);
        var load_url = $select.attr("data-load-url");
        return $select.selectize({
            onInitialize: function () {
                // html5 data attributes are wiped.  This is a workaround.
                var s = this;
                this.revertSettings.$children.each(function () {
                    $.extend(s.options[this.value], $(this).data());
                });

                // the calculator for the input grid needs to know the rate associated
                // with the chosen vat code.  So it can easily grab the rate i just add
                // the rate as data-rate to the select element itself every time it changes.
                // This does the same when the page loads.
                var selected_value = this.items[0];
                if (selected_value) {
                    var selected_option = this.options[selected_value];
                    if (selected_option) {
                        $select.attr("data-rate", selected_option["rate"]);
                    }
                }
            },
            create: function (input, callback) {
                var self = this;
                var selectize_callback_adapter = function (data) {
                    if (data.success) {
                        callback(data.new_object);
                    } else {
                        callback({});
                    }
                }
                // so it isn't garbage collected
                modal = new ModalForm({
                    modal: $("#new-vat_code"),
                    callback: selectize_callback_adapter,
                })
            },
            openOnFocus: true,
            valueField: 'id',
            labelField: 'code',
            searchField: 'code', // if this is not properly defined it can cause the dropdown to not open on searching
            dropdownParent: 'body', // this is so the dropdown is visible if the select menu is inside an insufficiently sized parent element
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
            },
            onChange: function (value) {
                var self = this;
                var option = this.getOption(value);
                var rate = option.attr("data-rate");
                $select.attr("data-rate", rate);
            }
        });
    }


    function group_options(selectize_instance, data) {
        selectize_instance.clearOptionGroups();
        selectize_instance.clearOptions();
        $.each(data, function (index, value) {
            selectize_instance.addOptionGroup(value["group_label"], {
                label: value["group_label"],
                value: value["group_label"]
            });
        });
    }


    function nominal(select_menu) {
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
        var load_url = $select.attr("data-load-url");
        return $select.selectize({
            create: function (input, callback) {
                var self = this;
                var selectize_callback_adapter = function (data) {
                    if (data.success) {
                        group_options(self, [data.new_object]);
                        callback(data.new_object);
                    } else {
                        callback({});
                    }
                }
                // so it isn't garbage collected
                modal = new ModalForm({
                    modal: $("#new-nominal"),
                    callback: selectize_callback_adapter,
                })
            },
            openOnFocus: true,
            valueField: 'opt_value',
            labelField: 'opt_label',
            searchField: 'opt_label', // was `name` but this means the dropdown doesn't appear as you type
            optgroupField: 'group_label',
            dropdownParent: 'body',
            lockOptgroupOrder: true,
            sortField: [{
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
                        group_options(self, res.data);
                        callback(res.data);
                    },
                });
            },
            render: {
                option_create: function (data, escape) {
                    return "<div class='create p-2'>Create new nominal: " + escape(data.input) + "</div>"
                }
            }
        });
    }


    return {
        nominal: nominal,
        vat: vat
    }

});
(function (root, module) {
    root.input_dropdown_widget = module();
})(window, function () {


    // NOTES -
    // When the widget opens the input field
    // will not necessarily be the same height
    // as the parent element - at least this is the case
    // with the <td> element - even though 100% height
    // is applied to the widget.
    // In such situations the code consuming this module
    // must make the change so the input field does
    // fill up the parent's height.

    // TO DO -
    // The selected option should have a highlighted color
    // It isn't as simple as coloring the one with the
    // data-selected attribute however as this effect
    // should be removed when we hover over another option.


    // GLOBAL LEVEL MODULE VARIABLES

    var last_widget_used;
    // Going through each of the widgets in the browser
    // is too slow.  So we know which to close down
    // when a new one is used we keep track here.
    var new_btn_selector; // dropdowns can have a button / link
    // for creating new content on the fly
    var parents_selector; // parent selector identifier
    // this will be "td" for our implementation by default
    var validate_on_server;

    function set_module_defaults(opts) {
        var opts = opts || {};
        parents_selector = opts.parents_selector || "td";
        new_btn_selector = opts.new_btn_selector || ".new-btn"
        validate_on_server = opts.validate_on_server || true;
    }

    function validate(url, chosen_value, callback) {
        // validate the choice on the server at the specified URL
        if (chosen_value) {
            var url = url + "&value=" + chosen_value;
            $.ajax({
                url: url,
                success: callback,
                error: callback
            });
        }
    }


    Widget.prototype.search = function () {
        var $widget = this.get_$dom();
        var url = $widget.find("input").attr("data-load-url");
        var $dropdown = $widget.find(".dropdown");
        $dropdown.children().not(new_btn_selector).remove();
        var search_for = $widget.find("input").val();
        if (search_for) {
            $.ajax({
                url: url + "&search=" + search_for,
                success: function (data) {
                    var $dropdown_options = $(data).find("li").not(new_btn_selector)
                    $dropdown.append($dropdown_options);
                    $dropdown.show();
                }
            });
        }
        $dropdown.attr("data-search", search_for || "");
        $dropdown.attr("data-page", 0);
    };


    Widget.prototype.open = function () {
        // open means the user can interact with widget
        var $widget = this.get_$dom();
        $widget.find(".label").hide();
        var parent_width = $widget.parents().eq(0).innerWidth();
        var dropdown_icon = $widget.find(".dropdown-btn");
        var shrink_by = dropdown_icon.outerWidth();
        $widget.find("input").width(parent_width - shrink_by);
        $widget.removeClass("position-relative");
        $widget.find(".input-wrapper")
            .removeClass("px")
            .height("100%")
            .addClass("data-input-focus-border");
        var label = $widget.find("label").text();
        $widget.find("input").val(label);
        last_widget_used = this;
    };

    Widget.prototype.close = function () {
        // close means the user has to focus on the widget
        // before they can interact
        var $widget = this.get_$dom();
        var $widget_input_elem = $widget.find("input");
        var default_label = $widget_input_elem.attr("data-default-label");
        var default_value = $widget_input_elem.attr("data-default-value");
        var chosen_label = $widget_input_elem.val();
        var chosen_value = $widget_input_elem.attr("data-choice-value");
        // chosen value is the one which corresponds to the chosen label
        // like on a native HTML select widget the label is what the
        // user picks and the value is the option value
        if (default_value == chosen_value) {
            return this.set_label_and_value(default_label, default_value);
        }
        var last_validated_value = $widget_input_elem.attr("data-last-validated-value");
        if (last_validated_value && last_validated_value == chosen_value) {
            var last_validated_label = $widget_input_elem.attr("data-last-validated-label");
            return this.set_label_and_value(last_validated_label, last_validated_value);
        }
        var validation_url = $widget_input_elem.attr("data-validation-url");
        var that = this;
        if (validate_on_server && validation_url) {
            validate(validation_url, chosen_value, function (data) {
                var label;
                var value;
                if (data.success) {
                    label = data.label;
                    value = data.value;
                } else {
                    label = data.label || "";
                    value = data.value || "";
                }
                $widget_input_elem.attr("data-last-validated-label", label);
                $widget_input_elem.attr("data-last-validated-value", value);
                return that.set_label_and_value(label, value);
            });
        }
    };

    Widget.prototype.get_$dom = function () {
        return this.$dom;
    };

    Widget.prototype.set_$dom = function ($widget) {
        return this.$dom = $widget;
    };

    Widget.prototype.is_$dom = function ($widget) {
        // compare whether two jQuery objects are in fact
        // the same dom elements
        return $widget == this.get_$dom();
    };

    Widget.prototype.remove_events = function () {
        var events = this.events;
        for (var i = 0; i < events.length; i++) {
            var elem = events[i]["elem"];
            var event = events[i]["event"];
            var callback = events[i]["callback"];
            elem.off(event, callback);
        }
    };

    Widget.prototype.destroy_cloned_dropdown = function () {
        $(".cloned-dropdown").remove();
    };

    Widget.prototype.set_label_and_value = function (label, value) {
        // will show the label fully inside a DIV element
        // and make the input element only a pixel high
        // we prefer this over hiding the input
        // so native browser tabbing is supported
        $widget = this.get_$dom();
        $widget.addClass("position-relative");
        $input_wrapper = $widget.find(".input-wrapper");
        $input_wrapper.addClass("px");
        $input_wrapper.removeClass("data-input-focus-border");
        $widget.find(".dropdown").hide();
        this.destroy_cloned_dropdown();
        $widget.find("input").val(value);
        $widget.find(".label")
            .text(label)
            .show();
        this.remove_events();
        $widget.find("input").trigger("change");
        last_widget_used = undefined;
    };


    Widget.prototype.clone_dropdown = function ($dropdown) {
        // clone and position the dropdown, rather
        var offset = $dropdown.offset();
        var clone = $dropdown.clone(true, true);
        clone.addClass("cloned-dropdown");
        clone.addClass("small");
        clone.css({
            "position": "relative",
            "top": offset.top,
            "left": offset.left
        });
        $("body").append(clone);
    };

    Widget.prototype.show_dropdown = function (event) {
        // this is called as an event listener
        // with 'this' bound to object instance
        var $widget = this.get_$dom();
        var $input = $widget.find("input");
        var $dropdown = $widget.find(".dropdown");
        // populate the dropdown menu
        var url = $input.attr("data-load-url");
        $dropdown.children().not(new_btn_selector).remove();
        var widget_instance = this;
        $.ajax({
            url: url,
            success: function (data) {
                var $dropdown_options = $(data);
                $dropdown.append($dropdown_options.find("li").not(new_btn_selector));
                widget_instance.clone_dropdown($dropdown);
            }
        });
        // show the dropdown menu
        $widget.find(".dropdown").toggle();
        event.stopPropagation();
    };

    Widget.prototype.update_choice = function (event) {
        // this is called within the context of an event firing
        // and 'this' is bound to the object instance
        $widget = this.get_$dom();
        var $event_target = $(event.target);
        if ($event_target.is("li")) {
            var label;
            var value = $event_target.attr("data-value");
            var data_attrs = $event_target.data(); // this includes all the data- attributes on the element but includes other things too
            // look for data-model attributes
            // note keys are now camel case
            // e.g. data-test-frog is now testFrog
            // so look for keys beginning with 'modelAttr'
            var $input = $widget.find("input");
            for (var key in data_attrs) {
                if (key.match("modelAttr")) {
                    $input.get(0).dataset[key] = data_attrs[key];
                }
            }
            if (value) {
                label = $event_target.text();
            } else {
                label = "";
            }
            $input.val(label);
            $input.attr("data-choice-value", value);
            this.close();
        }
        event.stopPropagation();
    };


    Widget.prototype.add_events = function (events) {
        this.events = events;
        for (var i = 0; i < events.length; i++) {
            var elem = events[i]["elem"];
            var event = events[i]["event"];
            var callback = events[i]["callback"];
            elem.on(event, callback);
        }
    };


    function Widget($widget) {
        this.$dom = $widget;

        this.add_events(
            [{
                    "elem": this.$dom.find(".dropdown-btn"),
                    "event": "click",
                    "callback": this.show_dropdown.bind(this)
                },
                {
                    "elem": this.$dom.find(".dropdown"),
                    "event": "click",
                    "callback": this.update_choice.bind(this)
                },
                {
                    "elem": this.$dom.find("input"),
                    "event": "keyup",
                    "callback": this.search.bind(this)
                },
            ]
        );

        var inst = infinite_scroll({
            container: this.$dom.find(".dropdown"),
            simple_bar: false,
            get_next_url: function (elem) {
                // elem is the element being scrolled
                var $elem = $(elem);
                var search = $elem.attr("data-search") || "";
                var last_page = $elem.attr("data-page");
                last_page = +last_page || 1;
                var next_page = last_page + 1;
                $elem.attr("data-page", next_page);
                var url = $widget.find("input").attr("data-load-url");
                if (url) {
                    return url + "&search=" + search + "&page=" + next_page;
                }
            },
            content_selector: function ($html) {
                return $html.find("li").not(new_btn_selector);
            },
            gap: 300
        });


        // add to the events so it can be re-added
        // when widget is re-opened
        this.events.push({
            "elem": this.$dom.find(".dropdown"),
            "event": "scroll",
            "callback": inst.old_callback
        });

    }

    function close_last_widget_used() {
        last_widget_used && last_widget_used.close();
    }


    function widget_focus(event) {
        $(this).find("input").focus();
        event.stopPropagation();
    }

    function widget_open(event) {
        var _parent = $(this);
        var $widget = _parent.find(".input-dropdown-widget-wrapper");
        if (last_widget_used && !last_widget_used.is_$dom($widget)) {
            last_widget_used.close();
        }
        var widget = new Widget($widget);
        widget.open();
        event.stopPropagation();
    }


    function init(opts) {

        set_module_defaults(opts);

        $("html").on("click", close_last_widget_used);

        $("[data-widget='input-dropdown-widget']")
            .parents(parents_selector)
            .on("click", widget_focus);
        // focuses on the input element inside the parent element
        $("[data-widget='input-dropdown-widget']")
            .parents(parents_selector)
            .on("focusin", widget_open);
        // focus event bubbles to parent where this event listener is fired

    }


    function add($new_dom_content) {

        $new_dom_content.find("[data-widget='input-dropdown-widget']")
            .parents(parents_selector)
            .on("click", widget_focus);

        $new_dom_content.find("[data-widget='input-dropdown-widget']")
            .parents(parents_selector)
            .on("click", widget_open);

    }

    return {
        init: init,
        add: add,
        close_input_dropdowns: close_last_widget_used
    }

});
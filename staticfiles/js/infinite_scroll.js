(function (root, module) {

    root.infinite_scroll = module();

})(window, function () {

    function debounce(func, wait, immediate) {
        var timeout;
        return function () {
            var context = this,
                args = arguments;
            var later = function () {
                timeout = null;
                if (!immediate) func.apply(context, args);
            };
            var callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func.apply(context, args);
        };
    };

    var last_request = {
        appended: true
    }
    var stop_requests = false;

    function load_and_append_content(url, options, elemBeingScrolled) {
        if (!stop_requests && url && last_request && last_request.appended) {
            last_request = {
                url: url,
                appended: false
            };
            $.ajax({
                url: url,
                success: function (data) {
                    var $html = $(data);
                    var wanted;
                    if(typeof(options.content_selector) == "string"){
                        wanted = $html.find(options.content_selector);
                    }
                    else if(typeof(options.content_selector == "function")){
                        wanted = options.content_selector($html);
                    }
                    if(options.append_to){
                        options.append_to.append(wanted);
                    }
                    else{
                        // if we do not have an element specified chosen to append to
                        // just append to the element being scrolled
                        $(elemBeingScrolled).append(wanted);
                    }
                    last_request.appended = true;
                    if (options.callback) {
                        options.callback();
                    }
                },
                error: function (data) {
                    // request for last_page + 1
                    // will cause error
                    stop_requests = true;
                }
            });
        }
    }


    return function api(options) {

        var gap = options.gap || 100;
        var body = $("body");
        var url;
        var $dom_element;
        var info = {}; // return this

        if ($.contains(body.get(0), options.container.get(0))) {

            function on_scroll() {
                var elem = $(this).get(0);
                if (elem.scrollHeight - $(this).scrollTop() <= $(this).outerHeight() + gap) {
                    url = options.get_next_url(this);
                    load_and_append_content(url, options, elem);
                }
            }

            var dom_element;

            if (options.simple_bar) {
                // per https://github.com/Grsmto/simplebar/tree/master/packages/simplebar
                var simple_bar_instance = SimpleBar.instances.get(options.container.get(0));
                dom_element = simple_bar_instance.getScrollElement();
                $dom_element = $(dom_element);
                // here dom_element will just be for one dom element
            } else {
                // whereas for here the dom element could be a jquery object
                // which corresponds to many dom elements
                // WE EXPECT A JQUERY OJBECT HERE UNLIKE IF WE ARE USING A SCROLLBAR IN CONDITION ABOVE
                $dom_element = options.container;
            }

            var new_callback = debounce(on_scroll, 50);

            if(options.old_callback){
                // in some situations we will need to recreate the
                // scroll event for our elements e.g. we create new elements
                // so we want to just add the scroll behaviour to all again from scratch i.e. reset
                $dom_element.off("scroll", options.old_callback);
            }

            info.old_callback = new_callback;

            $dom_element.on("scroll", new_callback);

        } else {

            function callback() {
                debounce(function () {
                    if ($(window).scrollTop() + $(window).height() >= $(document).height() - gap) {
                        url = options.get_next_url(this); // for sameness we pass the window object here but it's otherwise pointless.
                        // The calling function might as will define the get_next_url function so it just uses a top level
                        // scope variable which will be added to the window object anyway
                        load_and_append_content(url, options);
                    }
                }, 50)
            }

            if(options.old_callback){
                $(window).off("scroll", options.old_callback);
            }

            info.old_callback = callback;

            $(window).on("scroll", callback);
        }

        if (options.preFill) {
            url = options.preFillUrl();
            load_and_append_content(url, options);
        }

        return info;

    }

});
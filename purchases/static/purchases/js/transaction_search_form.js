(function (root, module) {
    root.transaction_search_form_init = module();
})(window, function () {

    function form_init() {
        var native_select_widget = $("select[data-selectize-type='contact']");
        var load_url = native_select_widget.attr("data-load-url");
        console.log(native_select_widget);
        contact_selectize({
            select_identifier: "select[data-selectize-type='contact']",
            load_url: load_url
        });
        $("select[name='search_within']").selectize();
    }

    return form_init;

});
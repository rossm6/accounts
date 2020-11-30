(function(root, module){
    root.transaction_search_form_init = module();
}(window, function(){

    function form_init() {
        cashbook_selectize($("select[name='cash_book']"));
    }

    return form_init;

}));
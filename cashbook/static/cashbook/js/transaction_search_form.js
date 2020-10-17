(function(root, module){
    root.transaction_search_form_init = module();
}(window, function(){

    return function form_init(){
        $("select[name='cashbook']").selectize();
    }

}));
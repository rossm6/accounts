(function(root, module){
    root.transaction_search_form_init = module();
}(window, function(){

    return function form_init(){
        input_grid_selectize.nominal($("div.adv-search-form select[data-selectize-type='nominal']"));
    }

}));
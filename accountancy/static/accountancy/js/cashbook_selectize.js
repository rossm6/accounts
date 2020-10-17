(function(root, module){
    root.cashbook_selectize = module();
})(window, function(){

    function cashbook(select_menu) {
        var $select = $(select_menu);
        var load_url = $select.attr("data-load-url");
        var modal;
        return $select.selectize({
            create: function (input, callback) {
                var self = this;
                var selectize_callback_adapter = function (data) {
                    if (data.success) {
                        callback(data.new_object);
                    } else {
                        callback({});
                    }
                }
                modal = new ModalForm({
                    modal: $("#new-cashbook"),
                    callback: selectize_callback_adapter,
                })
            },
            openOnFocus: true,
            valueField: 'id',
            labelField: 'name',
            searchField: 'name', // if this is not properly defined it can cause the dropdown to not open on searching
            dropdownParent: 'body', // this is so the dropdown is visible if the select menu is inside an insufficiently sized parent element
        });
    }

    return cashbook;

});
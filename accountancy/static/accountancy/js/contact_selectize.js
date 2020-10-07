// Requires:
// select_identifier = identifier for the native select widget
// creation_url = url for creating new contacts
// form = form identifier on server side to use for creating new contact
// form_field = field for form specified above
// load_url = url to get the contacts from


(function (root, module) {

    root.contact_selectize = module();

})(window, function () {

    return function init(opts) {

        var select_identifier = opts.select_identifier;
        var creation_url = opts.creation_url;
        var form_field = opts.form_field;
        var load_url = opts.load_url;

        return $(select_identifier).selectize({
            valueField: 'id',
            labelField: 'code',
            searchField: 'code',
            insert: true,
            create: function (input, callback) {
                var selectize_callback_adapter = function (data) {
                    if (data.success) {
                        callback(data.new_object);
                    } else {
                        callback({});
                    }
                }
                // so it isn't garbage collected
                modal = new ModalForm({
                    modal: $("#new-contact"),
                    callback: selectize_callback_adapter,
                })
            },
            load: function (query, callback) {
                $.ajax({
                    url: load_url,
                    type: 'GET',
                    dataType: 'json',
                    data: {
                        q: query,
                        page_limit: 10,
                    },
                    error: function () {
                        console.log("error loading suppliers...");
                    },
                    success: function (res) {
                        callback(res.data);
                    }
                });
            }
        });
    }

});
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
        var form = opts.form;
        var form_field = opts.form_field;
        var load_url = opts.load_url;

        return $(select_identifier).selectize({
            valueField: 'id',
            labelField: 'code',
            searchField: 'code',
            insert: true,
            create: function (input, callback) {
                $.ajax({
                    url: creation_url,
                    method: "POST",
                    // here we hard code the form prefix 'supplier'
                    data: "form=" + form + "&" + form_field + "=" + input + "&csrfmiddlewaretoken=" + Cookies.get('csrftoken'),
                    success: function (data) {
                        if (data.success) {
                            callback({
                                id: data.result.id,
                                code: data.result.text
                            });
                            // spent ages on this
                            // selectize.js says the keys should be value and text but according to below this is wrong
                            // https://github.com/selectize/selectize.js/issues/1329#issuecomment-358857146
                            // https://stackoverflow.com/questions/24366365/creating-an-item-if-not-already-exists-in-selectize-js-select-box-and-ajax-updat
                        }
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        console.log("There was an error creating the new item", jqXHR, textStatus, errorThrown);
                        callback({
                            id: '',
                            code: ''
                        });
                    }
                });
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
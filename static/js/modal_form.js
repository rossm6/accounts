(function(root, module) {

    root.ModalForm = module();

})(window, function() {

    // This is just called whenever the selectize calls its own method create
    // Whenever create is called again therefore we'll have another modal instance

    // either we create successful and the events are removed
    // the form fails and so a new form is inserted into the dom
    // the server returns an error and we remove the events

    ModalForm.prototype.create = function(event) {
        event.preventDefault();
        event.stopPropagation();
        var self = this;
        $.ajax({
            url: self.form.attr("action"),
            method: "POST",
            data: self.form.serialize(),
            success: function(data) {
                if (data.success) {
                    self.callback(data);
                    self.hide();
                } else {
                    self.remove_form_events();
                    var form = data.form_html;
                    form = $(form);
                    self.modal.find("form").replaceWith(form);
                    // look for any select element and selectize it
                    self.modal.find("select").selectize();
                    self.set_up_form(form);
                    self.callback(data);
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("There was an error creating the new item", jqXHR, textStatus, errorThrown);
                self.callback({});
                self.hide();
            }
        });

    };

    ModalForm.prototype.hide = function () {
        this.modal.modal("hide");
    };

    ModalForm.prototype.is_hidden = function () {
        this.remove_form_events();
        this.modal.off("hidden.bs.modal", this.is_hidden.bind(this));
        this.destroy();
    };

    ModalForm.prototype.cancel = function() {
        // it seems we have to call callback else it breaks the plugin
        // so we just pass an empty value and text
        this.callback({});
        this.remove_form_events();
        this.modal.modal("hide");
    };

    ModalForm.prototype.add_form_events = function () {
        this.form_submit_callback = this.create.bind(this);
        this.form.on("submit", this.form_submit_callback);
        this.cancel_btn_callback = this.cancel.bind(this);
        this.cancel_btn.on("click", this.cancel_btn_callback);
    };

    ModalForm.prototype.set_up_form = function ($form) {
        this.form = $form;
        this.cancel_btn = this.form.find(".btn.cancel")
        this.form.trigger("reset"); // note that if the form is swapped for the
        // form with errors then the default form is the one with errors
        // reset therefore will not blank out all the fields
        // leave this for now
        this.add_form_events();
    };

    ModalForm.prototype.remove_form_events = function() {
        this.form.off("submit", this.form_submit_callback);
        this.cancel_btn.off("click", this.cancel_btn_callback);
    };

    ModalForm.prototype.destroy = function () {
        this.modal.modal("dispose");
    }

    function ModalForm(opts) {
        // a new modal form instance should be created by the calling code
        this.modal = opts.modal;
        this.callback = opts.callback;
        this.modal.modal("show");
        this.set_up_form(this.modal.find("form"));
        this.modal.on("hidden.bs.modal", this.is_hidden.bind(this));
    }

    return ModalForm;

});
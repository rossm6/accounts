(function(root, module){

    root.ModalForm = module();

})(window, function(){

    ModalForm.prototype.create = function (event) {
        event.preventDefault();
        event.stopPropagation();
        var self = this;
        $.ajax({
            url: self.form.attr("action"),
            method: "POST",
            data: self.form.serialize(),
            success: function (data) {
                if(data.success) {
                    self.callback(data);
                    self.remove_events();
                }
                else{
                    var form = data.form_html;
                    self.modal.find("form").replaceWith($(form));
                    // look for any select element and selectize it
                    self.modal.find("select").selectize();
                    // do not remove the events
                    self.callback(data);
                }
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.log("There was an error creating the new item", jqXHR, textStatus, errorThrown);
                self.callback(data);
                self.remove_events();
            }
        });
    };

    ModalForm.prototype.cancel = function () {
        // it seems we have to call callback else it breaks the plugin
        // so we just pass an empty value and text
        this.callback({});
        this.remove_events();
    };


    ModalForm.prototype.remove_events = function () {
        this.form.off("submit", this.create);
        this.cancel_btn.off("click", this.cancel);
        this.modal.modal("hide");
    };

    function ModalForm (opts) {
        alert("modal");
        this.modal = opts.modal;
        this.callback = opts.callback;
        this.form = this.modal.find("form");
        this.cancel_btn = this.modal.find("button.cancel");
        this.modal.modal("show");
        this.form.on("submit", this.create.bind(this));
        this.cancel_btn.on("click", this.cancel.bind(this));
        var self = this;
        this.modal.on("hidden.bs.modal", function(){
            self.form.trigger("reset");
        });
    }

    return ModalForm;

});
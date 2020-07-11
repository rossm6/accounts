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
            data: "form=" + self.form.attr("data-form") + "&" + self.form.serialize(),
            success: function (result) {
                console.log(result);
                if(result) {
                    self.callback(result);
                }
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.log("There was an error creating the new item", jqXHR, textStatus, errorThrown);
                self.callback();
            },
            complete: function (jqXHR, textStatus) {
                self.remove_events();
            }
        });
    };

    ModalForm.prototype.cancel = function () {
        // it seems we have to call callback else it breaks the plugin
        // so we just pass an empty value and text
        this.callback();
        this.remove_events();
    };


    ModalForm.prototype.remove_events = function () {
        this.form.off("submit", this.create);
        this.cancel_btn.off("click", this.cancel);
        this.modal.modal("hide");
    };

    function ModalForm (opts) {
        this.modal = opts.modal;
        this.input = opts.input;
        this.callback = opts.callback;
        this.form = this.modal.find("form");
        this.cancel_btn = this.modal.find("button.cancel");
        this.modal.modal("show");
        cloned_form = this.modal.clone();
        this.form.on("submit", this.create.bind(this));
        this.cancel_btn.on("click", this.cancel.bind(this));
        var self = this;
        this.modal.on("hidden.bs.modal", function(){
            var parent = self.modal.parents().eq(0);
            self.modal.remove();
            parent.append(cloned_form);
        });
    }

    return ModalForm;

});
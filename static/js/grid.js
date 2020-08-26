(function (root, module) {

    root.Grid = module();

})(window, function () {


    Grid.prototype.delete_line = function (delete_button) {
        // assume delete button is in the line to delete
        // pretty dumb otherwise
        delete_button.parents("tr").eq(0).remove();
        this.set_total_forms(this.get_total_forms() - 1);
        this.reorder();
    };

    // calling code example
    // var grid = Grid(opts);
    // $(".delete_button").on("click", function(event){
    //     grid.delete_line();
    //     event.stopPropagation();
    // });


    Grid.prototype.reorder = function () {
        if (!this.order_lines) {
            console.log("WARNING: you have ordering diabled!");
        }
        var instance = this;
        this.get_table()
            .find("tbody")
            .find("tr")
            .not(this.empty_form_identifier)
            .each(function (index, element) {
                var element = $(element);
                var blank = true;
                element.find(":input:visible").each(function (index, field) {
                    var field = $(field);
                    if(field.attr("type") == "checkbox"){
                        if(field.prop("checked")){
                            blank = false;
                            return false;
                        }
                    }
                    else{
                        if(field.val()){
                            blank = false;
                            return false;
                        }
                    }

                });
                if (blank == false) {
                    // we only want to set ORDER on if all the fields are not blank
                    // otherwise server side validation will consider the form to have changed
                    // blank forms will then fail en masse
                    $(element)
                        .find("input" + instance.order_identifier)
                        .val(index);
                }
            });
    };


    Grid.prototype.add_many_lines = function (n) {
        for (var i = 0; i < n; i++) {
            this.add_line();
        }
    };


    Grid.prototype.add_line = function () {
        var next_line = this.get_empty_form().clone();
        var total_forms = this.get_total_forms();
        next_line = next_line.wrap("<p/>").parent().html();
        next_line = next_line.replace(/__prefix__/g, total_forms);
        next_line = $(next_line);
        next_line.removeClass("d-none").removeClass("empty-form");
        next_line.find("input").each(function () {
            $(this).val("");
        });
        if (this.order_lines) {
            next_line.find("input" + this.order_identifier).val(total_forms);
        }
        this.get_table().find("tbody").append(next_line);
        this.set_total_forms(total_forms + 1);
        if (this.add_callback) {
            this.add_callback(next_line);
        }
    };

    // calling code example
    // var grid = Grid(opts);
    // $(".add_invoice_button").on("click", function(event){
    //     grid.add_line();
    //     event.stopPropagation();
    // });


    Grid.prototype.set_total_forms = function (count) {
        $(this.form_identifier).find("input[name='" + this.prefix + "-TOTAL_FORMS']").val(count);
    };


    Grid.prototype.get_total_forms = function () {
        return +$(this.form_identifier).find("input[name='" + this.prefix + "-TOTAL_FORMS']").val();
    };


    Grid.prototype.get_table = function () {
        return $(this.table);
    };

    Grid.prototype.get_empty_form = function () {
        return $(this.table).find("tr" + this.empty_form_identifier);
    };


    function enable_jquery_sorting(grid) {
        grid.get_table().find("tbody").sortable({
            placeholder: "ui-state-highlight",
            handle: ".col-draggable-icon",
            update: function (event, ui) {
                grid.reorder();
            }
        });
        grid.get_table().find("tbody").disableSelection();
    }


    // Example options
    // {
    //     prefix: "line", // form prefix
    //     form_identifier: "lines", // wrapper for grid
    //     order_lines: true, // is ordering enabled
    //     order_identifier: ".ordering"
    //     empty_form_identifier: ".empty_form",
    //     add_callback: function called when a line has been added
    //                   is passed the new line
    // }


    function Grid(opts) {
        this.prefix = opts.form_prefix || "line";
        this.form_identifier = opts.form_identifier || "line";
        this.empty_form_identifier = opts.empty_form_identifier || ".empty-form";
        // we expect the grid table to have the prefix
        this.table = "table." + this.prefix;
        this.order_lines = opts.order_lines || true;
        this.order_identifier = opts.order_identifier || ".ordering";
        if (this.order_lines) {
            enable_jquery_sorting(this);
        }
    }


    return Grid;

});
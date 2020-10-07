$(document).ready(function () {

    // THIS SCRIPT ASSUMES THE INPUT_DROPDOWN WIDGET IS ASSUMED
    // MAY WANT TO MAKE THIS CONFIGURABLE LATER ON
    // LIKEWISE THE SUBMIT CALLBACK IS FOR A FORM ELEMENT
    // WITH A FORMSET CLASS
    // MIGHT WANT TO MAKE THIS CONFIGURABLE ALSO

    var line_form_prefix = "{{ line_form_prefix }}" || "form";

    // for entering transaction lines only
    var main_grid = new Grid({
        prefix: line_form_prefix,
        form_identifier: ".formset", // pluralise
        order_lines: true,
        order_identifier: ".ordering",
        empty_form_identifier: ".empty-form",
    });

    var selectized_menus = {}; // keep track of the menus we create so we can destroy them also when removing the lines

    function destory_selectized_menus ($tr) {
        // loop through input elements in row
        $tr.find(":input").each(function(index, elem){
            if (elem.name in selectized_menus){
                selectized_menus[elem.name][0].selectize.destroy();
                delete selectized_menus[elem.name];
            }
        });
    }
    
    $("div.lines :input")
    .filter(function(index){
        return this.name.match(/^line-\d+-nominal$/);
    })
    .focus(function(){
        if(!$(this).hasClass("selectized")){
            var s = input_grid_selectize.nominal(this);
            selectized_menus[this.name] = s;
        }
    });

    $("div.lines :input")
    .filter(function(index){
        return this.name.match(/^line-\d+-vat_code$/);
    })
    .focus(function(){
        if(!$(this).hasClass("selectized")){
            var s = input_grid_selectize.vat(this);
            selectized_menus[this.name] = s;
        }
    });

    function two_decimal_places(n_str) {
        if (n_str) {
            return parseFloat(n_str).toFixed(2);
        }
    }

    main_grid.add_callback = function (new_line) {
        new_line.find("td.col-close-icon").on("click", function () {
            main_grid.delete_line($(this));
        });
        new_line.on("change", "input[type=number]", function () {
            var n = two_decimal_places($(this).val());
            $(this).val(n);
        });
    };

    $(".add-lines").on("click", function (event) {
        main_grid.add_line();
        event.stopPropagation();
    });

    $(".add-multiple-lines").on("click", function (event) {
        var $target = $(event.target);
        var lines = $target.attr("data-lines");
        if (lines) {
            lines = +lines;
            main_grid.add_many_lines(lines);
        }
        event.stopPropagation();
    });

    {% if edit %}

    $("td.col-close-icon").on("click", function (event) {
        var $this = $(this);
        var $tr = $(this).parents("tr");
        var val = $tr.find("input.delete-line").get(0).checked;
        if (val) {
            $(this).parents("tr").find("input.delete-line").prop("checked", false);
            $tr.removeClass("deleted-row");
        } else {
            // if the line is not saved in the DB already just delete the line / row / form
            var id_input_field = $tr.find(":input").filter(function () {
                return this.name.match(/^line-\d+-id$/);
            });
            if (id_input_field && !id_input_field.val()) {
                main_grid.delete_line($this);
                destory_selectized_menus($(this).parents("tr").eq(0));
            } else {
                $(this).parents("tr").find("input.delete-line").prop("checked", true);
                $tr.addClass("deleted-row");
            }
        }
    });

    // in case the server returns errors loop through lines with deleted set
    // and change color
    $("td.col-close-icon").each(function () {
        var $tr = $(this).parents("tr");
        var val = $tr.find("input.delete-line").prop("checked");
        if (val) {
            $tr.addClass("deleted-row");
        } else {
            $tr.removeClass("deleted-row");
        }
    });

    {% else %}

    $("td.col-close-icon").on("click", function (event) {
        main_grid.delete_line($(this));
        destory_selectized_menus($(this).parents("tr").eq(0));
        event.stopPropagation();
    });

    {% endif %}

    $("html").on("click focusin", function () {
        $("table.line td").find("*").removeClass("data-input-focus-border");
    });

    $("table.line td").on("click focusin", function (event) {
        $("td").find("*").not($(this)).removeClass("data-input-focus-border");
        if ($(this).find(":input").hasClass("can_highlight")) {
            $(this).find(":input.can_highlight").addClass("data-input-focus-border");
            // the above won't work though for adding the border to the input with the selectized widget
            // so... we do this
            $(this).find("div.selectize-input").addClass("data-input-focus-border");
        }
        event.stopPropagation();
    });

    $("input[type=number]").each(function () {
        var n = two_decimal_places($(this).val());
        $(this).val(n);
    });

    $("input[type=number]").on("change", function () {
        var n = two_decimal_places($(this).val());
        $(this).val(n);
    });

});
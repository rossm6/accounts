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

    main_grid.add_callback = function (new_line) {
        input_dropdown_widget.add(new_line);
        new_line.find("td.col-close-icon").on("click", function () {
            main_grid.delete_line($(this));
        });
    };

    $(".add-lines").on("click", function (event) {
        main_grid.add_line();
        event.stopPropagation();
    });

    $(".add-multiple-lines").on("click", function (event) {
        var $target = $(event.target);
        var lines = $target.attr("data-lines");
        if(lines){
            lines = +lines;
            main_grid.add_many_lines(lines);
        }
        event.stopPropagation();
    });

    $("td.col-close-icon").on("click", function(event){
        main_grid.delete_line($(this));
        event.stopPropagation();
    });

    $("html").on("click focusin", function () {
        $("td input.can_highlight").removeClass("data-input-focus-border");
        input_dropdown_widget.close_input_dropdowns(); 
    });

    $("td").on("click focusin", function (event) {
        $("td input.can_highlight").not($(this)).removeClass("data-input-focus-border");
        if($(this).find("input").hasClass("can_highlight")){
            $(this).find("input").addClass("data-input-focus-border");
            input_dropdown_widget.close_input_dropdowns();
        }
        event.stopPropagation();
    });

    input_dropdown_widget.init();

    // var submit_ready = false;

    // $(".formset").on("submit", function(event) {
    //     if(!submit_ready){
    //         // we need to add new imputs which correspond to the matching
    //         var cont = $(".matching_transactions_formset");
    //         matching_transactions.create_inputs(cont);
    //         // new elements will not be part of form which jQuery object
    //         // which submit is currently firing on corresponds to
    //         submit_ready = true;
    //         $(".formset").submit();
    //     }
    //     else{
    //         return true; // i.e. submit 
    //     }
    // });



});
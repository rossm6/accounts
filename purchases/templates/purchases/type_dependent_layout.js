$(document).ready(function(){

    var header_prefix = "{{ header_form_prefix }}";

    function adjust_layout(type) {
        var due_date = $("input[name='" + header_prefix + "-due_date']").parents("div.form-group");
        var line_formset = $("div.lines");
        if(type == "bf" || type == "p" || type == "br" || type == "r"){
            due_date.hide();
            line_formset.hide();
        }
        else{
            due_date.show();
            line_formset.show();
        }
    }

    $("select[name='header-type']").on("change", function(){
        var type = $(this).val();
        adjust_layout(type);
    });

});
$(document).ready(function(){

    $("div.has_errors").mouseover(function(){
        var errors = $(this).find(".error-tooltip").clone();
        var field_error = $(".field_error");
        var wrapper = field_error.parents("div.field_errors_wrapper").eq(0);
        field_error.empty();
        field_error.append(errors.children());
        wrapper.fadeIn("slow", function(){  });
    });

    $("div.has_errors").mouseleave(function(){
        var field_error = $(".field_error");
        var wrapper = field_error.parents("div.field_errors_wrapper").eq(0);
        wrapper.hide();
    });

});
$(document).ready(function () {

    var table = $("table.audits").DataTable({
        dom: "t",
        paging: false
    });

    var edit_mode = "{{ edit_mode }}";
    var header_aspect_audit_style_class = "header_aspect_audit";
    var line_aspect_audit_style_class = "line_aspect_audit";
    var match_aspect_audit_style_class = "match_aspect_audit";

    function position_highlighter(el, highlighter){
        var rect = el.get(0).getBoundingClientRect();
        highlighter.css({
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
            "position": "fixed"
        });
    }

    function highlight_element (el, cls) {
        var highlighter = $("<div>");
        highlighter.addClass("audit_highlighter").addClass(cls);
        position_highlighter(el, highlighter);
        $("body").append(highlighter);
        $(window).on("scroll", function(){
            position_highlighter(el, highlighter);
        });
    }

    function removeAuditEffects() {
        $("div.audit_highlighter").remove();
    }

    function find_line_or_match_item($elem, match_regex, object_pk){
        // filter dom descendants based on whether we are editing or viewing transaction
        if(edit_mode){
            return (
                $elem
                .find(":input")
                .filter(function (index) {
                    return this.name.match(match_regex);
                })
                .filter(function (index) {
                    return this.value == object_pk
                })
            )
        }
        else{
            return (
                $elem
                .find("td[data-pk=" + object_pk + "]")
            )
        }
    }

    $("table.audits tbody tr").on("click", function () {
        var aspect = $(this).attr("data-audit-aspect"); // e.g. header, line, match.  
        // Not relevant for single object audits like contact, nominals etc 
        var audit_pk = $(this).attr("data-audit-pk");
        $("div.audit_fields").children().addClass("d-none");
        var details;
        if (aspect) {
            var object_pk = $(this).attr("data-object-pk");
            details = $("div.audit_fields").find("[data-audit-aspect=" + aspect + "][data-audit-pk=" + audit_pk + "]");
            // we need to also add a border to the relevant object in the UI so the user knows which
            // object the audit refers to

            // remove previous effects
            removeAuditEffects();

            if (aspect == "header") {
                var el = $("[data-audit-aspect-section=" + aspect + "]");
                if (el.length) {
                    // only do this if the element exists.
                    // for header this cannot not be but for line and match it could be because the line or
                    // match could have been deleted
                    el.get(0).scrollIntoView();
                    highlight_element(el, header_aspect_audit_style_class);
                }
            } else if (aspect == "line") {

                var el = (
                    find_line_or_match_item(
                        $("[data-audit-aspect-section=" + aspect + "]"),
                        RegExp("line-\\d+-id"),
                        object_pk
                    )
                    .parents("tr")
                    .eq(0)
                );

                if(el.length){
                    el.get(0).scrollIntoView();
                    highlight_element(el, line_aspect_audit_style_class);
                }

            } else {
                var el = (
                    find_line_or_match_item(
                        $("[data-audit-aspect-section=" + aspect + "]"),
                        RegExp("match-\\d+-id"),
                        object_pk
                    )
                    .parents("tr")
                    .eq(0)
                );
                if(el.length){
                    el.get(0).scrollIntoView();
                    highlight_element(el, match_aspect_audit_style_class);
                }

            }
        } else {
            details = $("div.audit_fields").find("[data-audit-pk=" + audit_pk + "]");
        }
        details.removeClass("d-none");
    });


    // remove any effects when audit modal is closed
    $("#auditModal").on("hide.bs.modal", function (e) {
        removeAuditEffects();
        $(window).scrollTop(0);
    });


});
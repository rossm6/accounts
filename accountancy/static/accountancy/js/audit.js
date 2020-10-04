$(document).ready(function () {

    var table = $("table.audits").DataTable({
        dom: "t",
    });

    var header_aspect_audit_style_class = "header_aspect_audit";
    var line_aspect_audit_style_class = "line_aspect_audit";
    var match_aspect_audit_style_class = "match_aspect_audit";

    function removeAuditEffects() {
        $("[data-audit-aspect-section=header]").removeClass(header_aspect_audit_style_class);
        $("[data-audit-aspect-section=line]")
            .find("tr")
            .removeClass(line_aspect_audit_style_class);
        $("[data-audit-aspect-section=match]")
            .find("tr")
            .removeClass(match_aspect_audit_style_class);
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
                var el = $("[data-audit-aspect-section=" + aspect + "]")
                    .addClass(header_aspect_audit_style_class);
                if (el.length) {
                    // only do this if the element exists.
                    // for header is this cannot not be but for line and match it could be because the line or
                    // match could have been deleted
                    el.get(0).scrollIntoView();
                }
            } else if (aspect == "line") {

                var el = $("[data-audit-aspect-section=" + aspect + "]")
                    .find(":input")
                    .filter(function (index) {
                        return this.name.match(/line-\d+-id/);
                    })
                    .filter(function (index) {
                        return this.value == object_pk
                    })
                    .parents("tr")
                    .eq(0)
                    .addClass(line_aspect_audit_style_class);
                    
                if(el.length){
                    el.get(0).scrollIntoView();
                }

            } else {

                var el = $("[data-audit-aspect-section=" + aspect + "]")
                    .find(":input")
                    .filter(function (index) {
                        return this.name.match(/match-\d+-id/);
                    })
                    .filter(function (index) {
                        return this.value == object_pk
                    })
                    .parents("tr")
                    .eq(0)
                    .addClass(match_aspect_audit_style_class);

                if(el.length){
                    el.get(0).scrollIntoView();
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
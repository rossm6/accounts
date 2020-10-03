$(document).ready(function () {

    var table = $("table.audits").DataTable({
        dom: "t",
    });

    $("table.audits tbody tr").on("click", function () {
        var aspect = $(this).attr("data-audit-aspect"); // e.g. header, line, match.  
        // Not relevant for single object audits like contact, nominals etc 
        var audit_pk = $(this).attr("data-audit-pk");
        $("div.audit_fields").children().addClass("d-none");
        var details;
        if(aspect){
            details = $("div.audit_fields").find("[data-audit-aspect=" + aspect + "][data-audit-pk=" + audit_pk + "]");
        }
        else{
            details = $("div.audit_fields").find("[data-audit-pk=" + audit_pk + "]");
        }
        details.removeClass("d-none");
    });

});
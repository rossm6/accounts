$(document).ready(function () {

    var table = $("table.audits").DataTable({
        dom: "t",
    });

    $("table.audits tr").on("click", function () {
        var audit_pk = $(this).attr("data-audit-pk");
        $("div.audit_fields").children().addClass("d-none");
        var details = $("div.audit_fields").find("[data-audit-pk=" + audit_pk + "]");
        details.removeClass("d-none");
    });

});
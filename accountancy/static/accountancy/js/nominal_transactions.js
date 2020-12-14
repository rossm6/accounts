$(document).ready(function() {

    var table = $("table.nominal_transactions").DataTable({
        dom: "t",
        scrollY: "1000px",
        language: {
            emptyTable: "This transaction must be a brought forward."
        },
        scrollCollapse: true,
        paging: false
    });

    $('#nominalTransactions').on('show.bs.modal', function(e) {
        table.columns.adjust();
    });

});
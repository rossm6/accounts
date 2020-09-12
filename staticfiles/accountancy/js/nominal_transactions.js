$(document).ready(function(){

    var table = $("table.nominal_transactions").DataTable({
        dom: "t",
        scrollY: "200px",
        language: {
            emptyTable: "This transaction must be a brought forward."
        },
        scrollCollapse: true
    });

    $('#nominalTransactions').on('show.bs.modal', function (e) {
        table.columns.adjust();
    });

});
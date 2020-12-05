var existing_matched_transactions_table = $("table.existing_matched_transactions").DataTable({
    dom: "t",
    bPaginate: false,
    columnDefs: [
        { orderDataType: 'dom-text', targets: [ 7 ] }, // this requires a plugin - see above and https://datatables.net/plug-ins/sorting/custom-data-source/dom-text
        { className: 'd-none', targets: [ 5, 6, 8 ] },
    ],
    scrollY: "200px",
    scrollCollapse: true,
    paging: false,
    language: {
        emptyTable: "This transaction isn't matched to anything yet"
    }
});
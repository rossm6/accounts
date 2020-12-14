$(document).ready(function(){

    var table = $("table.perms_table").DataTable({
        paging: false,
        dom: "t",
        order: [
            [0, 'asc'],
            [1, 'asc'],
            [2, 'asc']
        ],
        rowGroup: {
            dataSrc: [0,1],
            emptyDataGroup: null,

        },
        columnDefs: [
            { targets: [0, 1], visible: false},
        ]
    });

    $("table.perms_table tbody tr").addClass("pointer");
    $("table.perms_table tbody tr").not(".dtrg-group.dtrg-start.dtrg-level-0").toggleClass("collapse");
    $("table.perms_table tbody tr").on("click", function(){
        var $tr = $(this);
        if($tr.hasClass("dtrg-level-0")){
            var $siblings = $tr.nextAll();
            $siblings.each(function(index, elem){
                var $sibling = $(elem);
                if($sibling.hasClass("dtrg-level-0")){
                    return false;
                }
                $sibling.toggleClass("collapse");
            });
        }
    });

});
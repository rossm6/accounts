$(document).ready(function () {


    function calculate_vat(goods, vat_rate) {
        if (goods && vat_rate) {
            return ((+goods * 100 * +vat_rate) / (100 * 100)).toFixed(2);
        }
        return "";
    }

    function get_elements(tr) {
        var goods = tr.find(":input").filter(function (index) {
            return this.name.match(/line-\d+-goods/);
        });
        var vat_code = tr.find(":input").filter(function (index) {
            return this.name.match(/line-\d+-vat_code/);
        });
        var vat = tr.find(":input").filter(function (index) {
            return this.name.match(/^line-\d+-vat$/);
        });
        return {
            goods: goods,
            vat_code: vat_code,
            vat: vat
        };
    }

    function calculate_totals() {
        // first calculate the totals for goods, vat and total
        var lines = $("table.line").find("tbody").find("tr").not("tr.empty-form");
        var goods = 0;
        var vat = 0;
        lines.each(function (index, line) {
            var elements = get_elements($(line));
            var g = (+elements.goods.val() || 0) * 100;
            var v = (+elements.vat.val() || 0) * 100;
            goods = goods + g;
            vat = vat + v;
        });
        var total = goods + vat;
        goods = goods / 100;
        vat = vat / 100;
        total = total / 100;
        // second calculate the totals for matched and due
        var existing_matches = $("table.existing_matched_transactions").find("tbody").find("tr").not("tr.empty-form");
        var new_matches = $("table.new_matched_transactions").find("tbody").find("tr").not("tr.empty-form");
        var matched_total = 0;
        existing_matches.each(function (index, tr) {
            var elem = $(tr).find(":input").filter(function (index) {
                return this.name.match(/match-\d+-value/);
            });
            matched_total = matched_total + ((+elem.val() || 0) * 100);
        });
        new_matches.each(function (index, tr) {
            var elem = $(tr).find(":input").filter(function (index) {
                return this.name.match(/match-\d+-value/);
            });
            matched_total = matched_total + ((+elem.val() || 0) * 100);
        });
        matched_total = matched_total / 100;
        var due = total + matched_total;
        var invalid_matching_error_class = undefined;
        if((total >= 0 && due > total) || (total <= 0 && due < total)){
            // invalid matching
            invalid_matching_error_class = "bg-danger"
        }
        goods = goods.toFixed(2);
        vat = vat.toFixed(2);
        total = total.toFixed(2);
        $("td.goods-total-lines").text(goods);
        $("td.vat-total-lines").text(vat);
        $("td.total-lines").text(total);
        matched_total = matched_total.toFixed(2);
        due = due.toFixed(2)
        var matched_total_elem = $("td.matched-total");
        var due_total_elem = $("td.due-total");
        matched_total_elem.text(matched_total);
        due_total_elem.text(due);
        // if(invalid_matching_error_class){
        //     matched_total_elem.addClass(invalid_matching_error_class);
        //     due_total_elem.addClass(invalid_matching_error_class);
        // }
        // else{
        //     matched_total_elem.removeClass(invalid_matching_error_class);
        //     due_total_elem.removeClass(invalid_matching_error_class);  
        // }
    }

    $("table.line").on("change", ":input", function (event) {

        var input = $(this);
        var tr = input.parents("tr").eq(0);
        var elements = get_elements(tr);

        // calculate the VAT if the user changed value in field other than vat
        // because they may want to override

        if (
            !(
                $(this).filter(function (index) {
                    return this.name.match(/^line-\d+-vat$/);
                }).length
            )
        ) {

            elements.vat.val(
                calculate_vat(
                    elements.goods.val(),
                    elements.vat_code.attr("data-model-attr-rate")
                )
            );
            event.stopPropagation();

        }

        calculate_totals();

    });


    $("table.existing_matched_transactions").on("change", "input", function (event) {
        event.stopPropagation();
        calculate_totals();
    });

    $("table.new_matched_transactions").on("change", "input", function (event) {
        event.stopPropagation();
        calculate_totals();
    });

    // on page load.  So either for editing, or errors returned when
    // trying to create
    calculate_totals();

});
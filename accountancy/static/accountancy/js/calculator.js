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
        goods = goods.toFixed(2);
        vat = vat.toFixed(2);
        total = total.toFixed(2);
        $("div.sub-total-lines").text(goods);
        $("div.vat-total-lines").text(vat);
        $("div.total-lines").text(total);
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
});
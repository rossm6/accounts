(function (root, module) {

    root.TableFormset = module();

})(window, function () {

    // Example (original) use case -
    // jQuery datatable scroller draws the table on the fly while the user scrolls
    // To know whether to check a checkbox we need to do a look up
    // I envisage doing a lookup in the DOM for possibily hundreds of dom elements will be way too slow
    // This module therefore just keeps a dictionary of the dom elements with methods for looking up, adding and deleting

    TableFormset.prototype.lookup = function (key) {
        if(this.forms[key]){
            return true;
        }
        else{
            return false;
        }
    };


    TableFormset.prototype.get_empty_form = function () {
        if(this.empty_form){
            return this.empty_form;
        }
        var table_div_wrapper = this.formset.table().container();
        var table_div_wrapper = $(table_div_wrapper);
        var empty_form = table_div_wrapper.find("tbody").find("tr" + this.empty_form_identifier);
        this.empty_form = empty_form;
        return empty_form;
    };


    TableFormset.prototype.get_empty_form_as_string = function () {
        var empty_form = this.get_empty_form();
        var new_row = empty_form.clone();
        new_row.removeClass("d-none").removeClass(this.empty_form_identifier.substr(1)); 
        new_row = new_row.wrap("<p/>").parent().html();
        return new_row;
    };


    TableFormset.prototype.get_total_forms = function () {
        var management_form = this.management_form;
        return management_form.find("input[name=" + this.form_prefix + "-TOTAL_FORMS" + "]").val();
    };


    TableFormset.prototype.set_total_forms = function (total) {
        var management_form = this.management_form;
        management_form.find("input[name=" + this.form_prefix + "-TOTAL_FORMS" + "]").val(total);
    };


    TableFormset.prototype.add = function (key, new_row) {
        if (!this.forms[key]) {
            this.formset.row.add(new_row).draw();
            this.forms[key] = new_row;
        }
    };


    TableFormset.prototype.delete = function (key) {
        if (key in this.forms) {
            var row = this.forms[key];
            this.formset.row(row).remove().draw();
            delete this.forms[key];
            var form_no = this.get_total_forms();
            this.set_total_forms(form_no - 1);
        }
    };

    // danger here is we create a form and increment the total count
    // but the form is not added
    TableFormset.prototype.create = function (fields) {
        var form_no = +this.get_total_forms();
        var new_row = this.get_empty_form_as_string();
        new_row = new_row.replace(/__prefix__/g, form_no);
        new_row = $(new_row);
        var inputs = new_row.find(":input");
        for (var field in fields) {
            var value = fields[field].value;
            var field_in_form = this.form_prefix + "-" + form_no + "-" + field;
            var input = inputs.filter(function(){
                return this.name == field_in_form;  
            });
            input.val(value);
            var span = $("<span class='d-none'>" + value + "</span>");
            input.parents("td").eq(0).append(span);
            // nice trick - https://stackoverflow.com/a/53929269
        }
        this.set_total_forms(form_no + 1);
        return new_row;
    };


    function find_unique_field(prefix, field) {
        var reg = new RegExp(prefix + '-\\d+-' + field);
        return function (elem) {
            return elem.name.match(reg);
        }
    }

    function init(instance, formset) {
        var table_div_wrapper = formset.table().container();
        var table_div_wrapper = $(table_div_wrapper);
        var trs = table_div_wrapper.find("tbody").find("tr").not(instance.trs_to_ignore);
        var forms = instance.forms;
        var unique_filter = instance.find_unique_field;
        trs.each(function (index, tr) {
            var tr = $(tr);
            var key = tr.find(":input")
                .filter(function (index) {
                    return unique_filter(this);
                })
                .val();
            if (key) {
                forms[key] = tr;
            }
        });
    }

    function TableFormset(opts) {
        this.formset = opts.table; // jQuery datatable containing the formset
        this.form_prefix = opts.form_prefix;
        this.trs_to_ignore = opts.trs_to_ignore; // empty-form usually
        this.empty_form_identifier = opts.empty_form_identifier;
        this.unique_field = opts.unique_field; // e.g. field containing the primary key of a transaction
        this.forms = {}; // the dictionary for quick look ups
        this.find_unique_field = find_unique_field(this.form_prefix, this.unique_field);
        this.management_form = opts.management_form;
        init(this, this.formset);
    }

    return TableFormset;

});
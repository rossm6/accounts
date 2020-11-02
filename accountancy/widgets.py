from django.forms.widgets import Select


class SelectWithDataAttr(Select):
    def __init__(self, attrs=None, choices=()):
        self.data_option_attrs = None
        if attrs and 'data-option-attrs' in attrs:
            self.data_option_attrs = attrs["data-option-attrs"]
            attrs.pop("data-option-attrs")
        super().__init__(attrs=attrs, choices=choices)

    def optgroups(self, name, value, attrs=None):

        """ 
        Return a list of optgroups for this widget. 

        This is very similar to the method we are overriding.
        """
        groups = []
        has_selected = False
        attrs = {} # overide because option does not inherit select

        for index, (option_value, option_label, *model_attrs) in enumerate(self.choices):
            if option_value is None:
                option_value = ''

            subgroup = []
            if isinstance(option_label, (list, tuple)):
                group_name = option_value
                subindex = 0
                choices = option_label
            else:
                group_name = None
                subindex = None
                choices = [(option_value, option_label)]
            groups.append((group_name, subgroup, index))

            for subvalue, sublabel in choices:
                selected = (
                    str(subvalue) in value and
                    (not has_selected or self.allow_multiple_selected)
                )
                has_selected |= selected

                if model_attrs:
                    model_attrs = model_attrs[0]
                    # additional model fields can be added to the widget option
                    if self.data_option_attrs:
                        # programmer has decided there should be some attrs added to the option
                        model_attrs_map = {k: v for k, v in model_attrs}
                        for attr_name in self.data_option_attrs:
                            # e.g. attr_name is rate (from vat model)
                            if attr_name in model_attrs_map:
                                if 'data-option-attrs' not in attrs:
                                    attrs["data-option-attrs"] = {}
                                attrs["data-option-attrs"].update({
                                    "data-" + attr_name: str(model_attrs_map[attr_name])
                                })

                subgroup.append(self.create_option(
                    name, subvalue, sublabel, selected, index,
                    subindex=subindex, attrs=attrs,
                ))
                if subindex is not None:
                    subindex += 1

        return groups

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        index = str(index) if subindex is None else "%s_%s" % (index, subindex)
        if attrs is None:
            attrs = {}
        option_attrs = self.build_attrs(
            self.attrs, attrs) if self.option_inherits_attrs else {}
        if selected:
            option_attrs.update(self.checked_attribute)
        if 'id' in option_attrs:
            option_attrs['id'] = self.id_for_label(option_attrs['id'], index)
        if 'data-option-attrs' in attrs:
            for attr_name, attr_value in attrs["data-option-attrs"].items():
                option_attrs[attr_name] = attr_value
        return {
            'name': name,
            'value': value,
            'label': label,
            'selected': selected,
            'index': index,
            'attrs': option_attrs,
            'type': self.input_type,
            'template_name': self.option_template_name,
            'wrap_label': True,
        }

    @staticmethod
    def _choice_has_empty_value(choice):
        """Return True if the choice's value is empty string or None."""
        value, _, *model_attrs = choice
        return value is None or value == ''

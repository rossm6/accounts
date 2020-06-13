import copy

from django.forms.widgets import TextInput, Widget


class InputDropDown(Widget):
    """

    Based heavily on the ChoiceWidget

    At a later point may be a good idea to inherit from ChoiceWidget
    instead.  But to begin with I wanted to inherit from Widget
    so i had a better chance of getting the widget working how
    i wanted it to.
    
    """

    template_name = "accountancy/widgets/input_with_dropdown.html"
    option_template_name = "accountancy/widgets/dropdown_options.html"
    option_inherits_attrs = False
    checked_attribute = {'data-selected': True}
    add_id_index = False

    def __init__(self, attrs=None, choices=()):
        attrs.update(
            {
                "data-widget": "input-dropdown-widget",
                "type": "text"
            }
        )
        super().__init__(attrs)
        self.choices = list(choices)

    def __deepcopy__(self, memo):
        obj = copy.copy(self)
        obj.attrs = self.attrs.copy()
        obj.choices = copy.copy(self.choices)
        memo[id(self)] = obj
        return obj

    def options(self, name, value, attrs=None):
        """Yield a flat list of options for this widgets."""
        for group in self.optgroups(name, value, attrs):
            yield from group[1]

    def subwidgets(self, name, value, attrs=None):
        """
        Yield all "subwidgets" of this widget. Used to enable iterating
        options from a BoundField for choice widgets.
        """
        value = self.format_value(value)
        yield from self.options(name, value, attrs)

    def optgroups(self, name, value, attrs=None):
        """Return a list of optgroups for this widget."""
        groups = []
        has_selected = False

        for index, (option_value, option_label) in enumerate(self.choices):
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
                    str(subvalue) == value and
                    not has_selected
                )
                has_selected |= selected
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
        return {
            'value': value,
            'label': label,
            'selected': selected,
            'index': index,
            'attrs': option_attrs,
            'template_name': self.option_template_name,
            'wrap_label': True,
        }


    def return_label(self, val, value, label):
        if val == value:
            if not val:
                return ""
            return label        


    def get_label(self, value):
        """

        Copes with the simple -

            (value, label)

            and the slightly more complex,

            (Asset, [(3, Bank Account), (4, Prepayments)]) i.e. account choices which are roots and leaves
            
        """

        for val, label in self.choices:
            if isinstance(label, list):
                for val, _label in label:
                    r = self.return_label(val, value, _label)
                    if r is not None:
                        return r
            else:
                r = self.return_label(val, value, label)
                if r is not None:
                    return r
        return ""

    def get_context(self, name, value, attrs):
        context = {}
        value = self.format_value(value)
        label = self.get_label(value)
        attrs.update(
            {
                "data-choice-value": value,
                "data-last-validated-label": label,
                "data-last-validated-value": value,
                "data-default-label": label,
                "data-default-value": value
            }
        )
        context['widget'] = {
            'name': name,
            'is_hidden': self.is_hidden,
            'required': self.is_required,
            'value': value,
            'attrs': self.build_attrs(self.attrs, attrs),
            'template_name': self.template_name,
            'label': label
        }
        context['widget']['optgroups'] = self.optgroups(
            name, context['widget']['value'], attrs)
        return context

    def format_value(self, value):
        if not value:
            return ''
        return value

    def use_required_attribute(self, initial):
        return False
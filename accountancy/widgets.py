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
    checked_attribute = { 'data-selected': True }
    add_id_index = False

    def __init__(self, attrs=None, choices=(), model_attrs={}):
        attrs.update(
            {
                "data-widget": "input-dropdown-widget",
                "type": "text" # FIX ME - this should be number sometimes
            }
        )
        super().__init__(attrs)
        self.choices = list(choices)
        self.model_attrs = model_attrs

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


    def build_data_model_attrs(self, model_attrs_and_values):
        attrs = { attr[0] : attr[1] for attr in model_attrs_and_values }
        tmp = {}
        for attr in attrs:
            if attr in self.model_attrs:
                # create a namespace model-attr
                tmp["data-model-attr-" + attr] = attrs[attr]
        return tmp

    def id_for_label(self, id_, index='0'):
        """

        This is taken from Choice Widget.  The same method
        on Widget only takes 1 position argument.

        Use an incremented id for each option where the main widget
        references the zero index.
        """
        if id_ and self.add_id_index:
            id_ = '%s_%s' % (id_, index)
        return id_


    def optgroups(self, name, value, attrs=None):
        """Return a list of optgroups for this widget."""
        groups = []
        has_selected = False

        for index, (option_value, option_label, *model_attrs_and_values) in enumerate(self.choices):
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
                model_attrs = None
                if model_attrs_and_values:
                    model_attrs = self.build_data_model_attrs(model_attrs_and_values[0])
                subgroup.append(self.create_option(
                    name, subvalue, sublabel, selected, index,
                    subindex=subindex, attrs=attrs, model_attrs=model_attrs
                ))
                if subindex is not None:
                    subindex += 1
        return groups

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None, model_attrs=None):
        index = str(index) if subindex is None else "%s_%s" % (index, subindex)
        if attrs is None:
            attrs = {}
        option_attrs = self.build_attrs(
            self.attrs, attrs) if self.option_inherits_attrs else {}
        if model_attrs:
            option_attrs.update(model_attrs)
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


    def get_label_and_model_attrs(self, value):

        """

        Copes with the simple -

            (value, label)

            and the slightly more complex,

            (Asset, [(3, Bank Account), (4, Prepayments)]) i.e. account choices which are roots and leaves
            
        """

        # FIXED - when data was sent via POST 'value' was a string
        # whereas val from self.choices is an integer
        # so we cast value to an integer

        try:
            value = int(value)
        except ValueError:
            value = ''

        l = ""
        attrs = {}
        for val, label, *model_attrs_and_values in self.choices:
            if isinstance(label, list):
                for val, _label, *model_attrs_and_values in label:
                    if l := self.return_label(val, value, _label):
                        if model_attrs_and_values:
                            attrs = self.build_data_model_attrs(model_attrs_and_values[0])
                        break
            else:
                if l := self.return_label(val, value, label):
                    if model_attrs_and_values:
                        attrs = self.build_data_model_attrs(model_attrs_and_values[0])
                    break
        return (l, attrs)
        

    def get_context(self, name, value, attrs):
        context = {}
        value = self.format_value(value)
        label, model_attrs = self.get_label_and_model_attrs(value)
        attrs.update(
            {
                "data-choice-value": value,
                "data-last-validated-label": label,
                "data-last-validated-value": value,
                "data-default-label": label,
                "data-default-value": value
            }
        )
        if model_attrs:
            attrs.update(model_attrs)
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
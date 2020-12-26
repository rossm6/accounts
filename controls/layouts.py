from crispy_forms.layout import LayoutObject, TEMPLATE_PACK
from django.shortcuts import render
from django.template.loader import render_to_string


class TableFormset(LayoutObject):
    template_name = "controls/create_fy_formset.html"

    def __init__(self, thead, formset_name_in_context, template=None):
        th_labels = []
        th_css_class = []
        for th in thead:
            if isinstance(th, str):
                th_labels.append(th)
                th_css_class.append("")
            else:
                th_labels.append(th["label"])
                th_css_class.append(th["css_class"])
            
        self.thead = [ {"label": label, "class": css_class} for label, css_class in zip(th_labels, th_css_class) ]

        self.formset_name_in_context = formset_name_in_context
        self.fields = []
        self.template = self.template_name
        if template:
            self.template = template

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK):
        formset = context[self.formset_name_in_context]
        return render_to_string(self.template, {"theads": self.thead, "formset": formset})

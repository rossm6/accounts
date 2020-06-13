from django.template import Library

register = Library()

@register.filter(name='get_label')
def get_label(fields, field):
    return fields[field].label

@register.filter(name='lookup')
def lookup(value, arg):
    return value[arg]
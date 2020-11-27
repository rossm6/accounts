from django.template import Library

register = Library()


@register.filter(name='get_period_of_fy')
def get_period_of_fy(fy_and_period):
    if fy_and_period:
        return fy_and_period[4:]
    return ""

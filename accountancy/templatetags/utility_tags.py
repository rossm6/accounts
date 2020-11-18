from urllib.parse import urlencode

from django.template import Library
from django.utils.encoding import force_str

register = Library()


def construct_query_string(context, query_params):
    # empty values will be removed
    query_string = context["request"].path
    if len(query_params):
        encoded_params = urlencode([
            (key, force_str(value))
            for (key, value) in query_params if value
        ])
        query_string += f"?{encoded_params}"
    return query_string


@register.simple_tag(takes_context=True)
def modify_query(context, *params_to_remove, **params_to_change):
    """Renders a link with modified current query parameters"""
    query_params = []
    get_data = context["request"].GET
    for key, last_value in get_data.items():
        value_list = get_data.getlist(key)
        if key not in params_to_remove:
            # don't add key-value pairs for params_to_remove
            if key in params_to_change:
                # update values for keys in params_to_change
                query_params.append((key, params_to_change[key]))
                params_to_change.pop(key)
            else:
                # leave existing parameters as they were
                # if not mentioned in the params_to_change
                for value in value_list:
                    query_params.append((key, value))
    # attach new params
    for key, value in params_to_change.items():
        query_params.append((key, value))
    return construct_query_string(context, query_params)


@register.filter(name='get_label')
def get_label(fields, field):
    return fields[field].label


@register.filter(name='lookup')
def lookup(value, arg):
    return value[arg]

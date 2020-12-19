from decimal import Decimal
from itertools import chain
from urllib.parse import quote

TWOPLACES = Decimal(10) ** -2
PERIOD = '202007'  # purchases testing had been done - thousands of lines of testing - when i realised period had not been added
# so it is added via the testing helper functions instead of passed in to the functions


def encodeURI(s):
    return quote(s, safe='~@#$&()*!+=:;,.?/\'')


def dict_to_url(d):
    # source -
    return _kv_translation(d, "", "")


def _kv_translation(d, line, final_str):
    for key in d:
        key_str = key if not line else "[{}]".format(key)
        if type(d[key]) is not dict:
            final_str = "{}{}{}={}&".format(final_str, line, key_str, d[key])
        else:
            final_str = _kv_translation(d[key], line + key_str, final_str)
    return final_str


def two_dp(n):
    """
    n could be an int or a float
    """
    return Decimal(n).quantize(TWOPLACES)


def add_and_replace_objects(objects, replace_keys, extra_keys_and_values):
    for obj in objects:
        for old_key in replace_keys:
            new_key = replace_keys[old_key]
            same_value = obj[old_key]
            obj[new_key] = same_value
            del obj[old_key]
        for extra in extra_keys_and_values:
            extra_key = extra
            extra_value = extra_keys_and_values[extra_key]
            obj[extra_key] = extra_value
    return objects


def get_fields(obj, wanted_keys):
    d = {}
    for key in wanted_keys:
        d[key] = obj[key]
    return d


def to_dict(instance):
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    for f in opts.many_to_many:
        data[f.name] = [i.id for i in f.value_from_object(instance)]
    return data


def create_header(prefix, form):
    data = {}
    for field in form:
        data[prefix + "-" + field] = form[field]
    return data


def create_formset_data(prefix, forms):
    data = {}
    for i, form in enumerate(forms):
        for field in form:
            data[
                prefix + "-" + str(i) + "-" + field
            ] = form[field]
    if forms:
        i = i + 1  # pk keys start
    else:
        i = 0
    management_form = {
        prefix + "-TOTAL_FORMS": i,
        prefix + "-INITIAL_FORMS": 0,
        prefix + "-MIN_NUM_FORMS": 0,
        prefix + "-MAX_NUM_FORMS": 1000
    }
    data.update(management_form)
    return data

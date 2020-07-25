PERIOD = '202007' # purchases testing had been done - thousands of lines of testing - when i realised period had not been added
# so it is added via the testing helper functions instead of passed in to the functions

def match(match_by, matched_to):
    headers_to_update = []
    matches = []
    match_total = 0
    for match_to, match_value in matched_to:
        match_total += match_value
        match_to.due = match_to.due - match_value
        match_to.paid = match_to.total - match_to.due
        matches.append(
            PurchaseMatching(
                matched_by=match_by, 
                matched_to=match_to, 
                value=match_value,
                period=PERIOD
            )
        )
        headers_to_update.append(match_to)
    match_by.due = match_by.total + match_total
    match_by.paid = match_by.total - match_by.due
    PurchaseHeader.objects.bulk_update(headers_to_update + [ match_by ], ['due', 'paid'])
    PurchaseMatching.objects.bulk_create(matches)
    return match_by, headers_to_update


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
    data[prefix + "-" + "period"] = PERIOD
    return data

def create_formset_data(prefix, forms):
    data = {}
    for i, form in enumerate(forms):
        for field in form:
            data[
                prefix + "-" + str(i) + "-" + field
            ] = form[field]
    if forms:
        i = i + 1 # pk keys start
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


def create_cancelling_headers(n, supplier, ref_prefix, type, value):
    """
    Create n headers which cancel out with total = value
    Where n is an even number
    """
    date = timezone.now()
    due_date = date + timedelta(days=31)
    headers = []
    n = int(n /2)
    for i in range(n):
        i = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            goods=value,
            discount=0,
            vat=0,
            total=value,
            paid=0,
            due=value,
            date=date,
            due_date=due_date,
            type=type,
            period=PERIOD
        )
        headers.append(i)
    for i in range(n):
        i = PurchaseHeader(
            supplier=supplier,
            ref=ref_prefix + str(i),
            goods=value * -1,
            discount=0,
            vat=0,
            total=value * -1,
            paid=0,
            due=value * -1,
            date=date,
            due_date=due_date,
            type=type,
            period=PERIOD
        )
        headers.append(i)
    return PurchaseHeader.objects.bulk_create(headers)    
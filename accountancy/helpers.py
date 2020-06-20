from django.urls import reverse_lazy

def delay_reverse_lazy(viewname, query_params=""):
    def _delay_reverse_lazy():
        return reverse_lazy(viewname) + ( "?" + query_params if query_params else "" )
    return _delay_reverse_lazy


def get_index_of_object_in_queryset(queryset, obj, key):
    try:
        for i, o in enumerate(queryset):
            if getattr(o, key) == getattr(obj, key):
                return i
    except:
        pass
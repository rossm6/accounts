from django.urls import reverse_lazy

def delay_reverse_lazy(viewname, query_params=""):
    def _delay_reverse_lazy():
        return reverse_lazy(viewname) + ( "?" + query_params if query_params else "" )
    return _delay_reverse_lazy
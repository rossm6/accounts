from controls.models import QueuePosts

d = { fullname : code for code, fullname in  QueuePosts.POST_MODULES}

class QueuePostsMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            module = request.resolver_match.app_name
            code = d[module]
            lock = QueuePosts.objects.select_for_update().filter(module=code)
        return super().dispatch(request, *args, **kwargs)
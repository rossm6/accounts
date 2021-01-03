from django.shortcuts import reverse
from django.http import Http404

class RestrictAdminToStaffMiddleware:
    """
    A middleware that restricts admin site access to logged in staff members
    i.e. staff must login like non-staff first then navigate to the admin
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(reverse("admin:index")):
            if request.user.is_authenticated:
                if not request.user.is_staff:
                    raise Http404
            else:
                raise Http404
        return self.get_response(request)
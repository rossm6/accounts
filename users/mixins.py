from json import dumps
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import reverse

from users.models import Lock, UserSession


class LockDuringEditMixin:
    """
    This lock mechanism is for the browser.  A POST request through the browser presupposes first a GET request.
    The GET request locks if another user has not already locked.  The POST request will be allowed if there is no lock or
    the user owns the lock.  If another tries to GET in the browser then get a modal window error telling them they cannot.

    For an API we wouldn't ever want to check for locks for the GET request, or create.  For POST we would only want to check
    if there is a lock and never create.
    """
    object_identifier = "object"

    def get_object_to_edit(self):
        return getattr(self, self.object_identifier)

    def get_or_create_lock(self, object_to_edit):
        content_type = ContentType.objects.get_for_model(object_to_edit)
        lock_object, created = (
            Lock.objects
            .select_related("user_session")
            .select_related("user_session__user")
            .get_or_create(
                content_type=content_type,
                object_id=object_to_edit.pk,
                defaults={
                    "user_session": UserSession.objects.filter(user=self.request.user).first()
                }
            )
        )
        return lock_object, created

    def get_lock(self, object_to_edit):
        content_type = ContentType.objects.get_for_model(object_to_edit)
        try:
            lock = (
                Lock.objects
                .select_related("user_session")
                .select_related("user_session__user")
                .get(content_type=content_type, object_id=object_to_edit.pk)
            )
            return lock
        except Lock.DoesNotExist:
            return

    def can_edit(self, lock, created):
        if created:
            return True
        if lock.user_session.user.pk == self.request.user.pk:
            return True

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        object_to_edit = self.get_object_to_edit()
        lock, created = self.get_or_create_lock(object_to_edit)
        if not self.can_edit(lock, created):
            locked_by_another = {
                "user": lock.user_session.user.username,
                "edited_at": lock.edited_at.strftime("%d-%m-%Y")
            }
            unlock_url = ""
        else:
            locked_by_another = ""
            unlock_url = reverse("users:unlock", kwargs={"pk": lock.pk})
        context_data["unlock_url"] = unlock_url
        context_data["locked_by_another"] = locked_by_another
        return context_data

    def post(self, request, *args, **kwargs):
        if hasattr(self, self.object_identifier):
            if lock := self.get_lock(getattr(self, self.object_identifier)):
                if not self.can_edit(lock, None):
                    error_message = render_to_string(
                        "messages.html", 
                        {
                            "messages": [f"Username: {lock.user_session.user.username} is already editing this."]
                        }
                    )
                    return JsonResponse({"error_message": error_message}, status=403)
        return super().post(request, *args, **kwargs)


class LockTransactionDuringEditMixin(LockDuringEditMixin):
    """
    Transactions e.g. invoices, payments, do not have a self.object attribute.
    Rather they use self.main_header
    """
    object_identifier = "main_header"
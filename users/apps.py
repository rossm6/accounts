from uuid import uuid4

from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_in, user_logged_out


def user_logged_in_handler(sender, request, user, **kwargs):
    from users.models import UserSession
    UserSession.objects.get_or_create(
        user=user,
        session_id=request.session.session_key
    )

def delete_user_session(sender, request, user, **kwargs):
    from users.models import UserSession
    user_sessions = UserSession.objects.filter(user = user)
    for user_session in user_sessions:
        user_session.session.delete()

class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        user_session = self.get_model("UserSession")
        user_logged_in.connect(user_logged_in_handler)
        user_logged_out.connect(delete_user_session)

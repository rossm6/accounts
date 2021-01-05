from uuid import uuid4

from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_in, user_logged_out
from simple_history.signals import pre_create_historical_record


def user_logged_in_handler(sender, request, user, **kwargs):
    from users.models import UserSession

    # if a user logs into the system in a browser,
    # then another attempts
    # it errors because the session has not key been saved
    # so request.session.session_key is None
    # I've opted to disallow normal sigin and admin sign
    # if a user is logged in
    UserSession.objects.get_or_create(
        user=user,
        session_id=request.session.session_key
    )

def delete_user_session(sender, request, user, **kwargs):
    from users.models import UserSession
    user_sessions = UserSession.objects.filter(user=user)
    for user_session in user_sessions:
        user_session.session.delete()


def zeus(sender, **kwargs):
    print(sender)
    print(kwargs)


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        user_session = self.get_model("UserSession")
        user_logged_in.connect(user_logged_in_handler)
        user_logged_out.connect(delete_user_session)
        pre_create_historical_record.connect(zeus)
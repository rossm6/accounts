from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import models
from simple_history import register

register(Group, app=__package__)
register(User, app=__package__)

"""
Unlike all the other models, bulk_delete will not work here.  This shouldn't be a problem.
"""


class UserSession(models.Model):
    # See - http://gavinballard.com/associating-django-users-sessions/
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)


class Lock(models.Model):
    """
    If a user attempts to edit an object already being edited we should show them a message
        'Record is already being edited by another user'

    This model simply keeps track of who is editing what.
    """
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    user_session = models.ForeignKey(UserSession, on_delete=models.CASCADE)
    edited_at = models.DateTimeField(auto_now_add=True)
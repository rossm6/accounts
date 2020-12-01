from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from simple_history import register

register(Group, app=__package__)
register(User, app=__package__)

"""
Unlike all the other models, bulk_delete will not work here.  This shouldn't be a problem.
"""

class Lock(models.Model):
    """
    If a user attempts to edit an object already being edited we should show them a message
        'Record is already being edited by another user'

    This model simply keeps track of who is editing what.
    """
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    # user = models.ForeignKey(User, on_delete=CASCADE)
    # will need to link to a new model which links the session created during login to the user
    # see - http://gavinballard.com/associating-django-users-sessions/
    edited_at = models.DateTimeField(auto_now_add=True)
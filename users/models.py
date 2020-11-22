from django.contrib.auth.models import User, Group
from simple_history import register

register(Group, app=__package__)
register(User, app=__package__)

"""
Unlike all the other models, bulk_delete will not work here.  This shouldn't be a problem.
"""
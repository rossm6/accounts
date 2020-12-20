from django.db import models
from accountancy.mixins import AuditMixin
from controls.validators import is_fy_year

class FinancialYear(AuditMixin, models.Model):
    financial_year = models.PositiveSmallIntegerField(validators=[is_fy_year], unique=True)

    class Meta:
        ordering = ['financial_year']


class Period(AuditMixin, models.Model):
    period = models.CharField(max_length=2)
    fy_and_period = models.CharField(max_length=6, null=True)
    month_end = models.DateField()
    # CharField is better than SmallIntegerField because often we'll need to split into year and period
    # e.g. 202001, which is the first period of FY 2020, would need spliting into 2020, 01 for business logic
    fy = models.ForeignKey(FinancialYear, on_delete=models.SET_NULL, null=True, related_name="periods")

    def __str__(self):
        if self.fy_and_period:
            return self.fy_and_period
        return ""

class QueuePosts(models.Model):
    """
    POST requests for each ledger should be queued to avoid concurrency when creating,
    editing or voiding transactions.

    Each view - create, edit and void - should SELECT_FOR_UPDATE the row which is the module / django app
    the view belongs to before any work is done.  This way the POST requests per module are queued.
    """
    POST_MODULES = [
        ('c', 'cashbook'),
        ('n', 'nominals'),
        ('p', 'purchases'),
        ('s', 'sales'),
    ]
    module = models.CharField(max_length=1, choices=POST_MODULES)
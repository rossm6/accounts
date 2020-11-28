from django.db import models
from accountancy.mixins import AuditMixin
from settings.validators import is_fy_year

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
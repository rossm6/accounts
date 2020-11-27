from django.db import models
from accountancy.mixins import AuditMixin


class FinancialYear(AuditMixin, models.Model):
    financial_year = models.CharField(max_length=4)  # e.g. 2020

    class Meta:
        ordering = ['financial_year']


class Period(AuditMixin, models.Model):
    period = models.CharField(max_length=6, null=True)
    month_end = models.DateField()
    # CharField is better than SmallIntegerField because often we'll need to split into year and period
    # e.g. 202001, which is the first period of FY 2020, would need spliting into 2020, 01 for business logic
    fy = models.ForeignKey(FinancialYear, on_delete=models.SET_NULL, null=True, related_name="periods")

    def __str__(self):
        if self.period:
            year = self.period[:4]
            period_in_fy = self.period[4:]
            return f"{period_in_fy} {year}"
        return "No period specified"

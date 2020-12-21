from accountancy.mixins import AuditMixin
from django.db import models

from controls.exceptions import MissingPeriodError
from controls.validators import is_fy_year


class FinancialYear(AuditMixin, models.Model):
    financial_year = models.PositiveSmallIntegerField(
        validators=[is_fy_year], unique=True)
    number_of_periods = models.PositiveIntegerField(default=12)

    class Meta:
        ordering = ['financial_year']


class Period(AuditMixin, models.Model):
    period = models.CharField(max_length=2)
    fy_and_period = models.CharField(max_length=6, null=True)
    month_end = models.DateField()
    # CharField is better than SmallIntegerField because often we'll need to split into year and period
    # e.g. 202001, which is the first period of FY 2020, would need spliting into 2020, 01 for business logic
    fy = models.ForeignKey(
        FinancialYear, on_delete=models.SET_NULL, null=True, related_name="periods")

    class Meta:
        ordering = ['fy_and_period']

    def __add__(self, other):
        fys = {
            fy.financial_year: {
                'fy': fy,
                'periods': list(fy.periods.all())
            }
            for fy in FinancialYear.objects.all()
        }
        fy_int, period_int = int(
            self.fy_and_period[:4]), int(self.fy_and_period[4:])
        while(other):
            n = fys[fy_int]["fy"].number_of_periods
            if(other > n - period_int):
                fy_int = fy_int + 1
                if fy_int in fys:
                    other = other - (n - period_int + 1)
                    period_int = int(fys[fy_int]["periods"][0].period)
                else:
                    raise MissingPeriodError("Next FY with periods is missing")
            elif other == (n - period_int):
                return fys[fy_int]["periods"][-1]
            else:
                return fys[fy_int]["periods"][period_int - 1 + other]

    def __sub__(self, other):
        fys = {
            fy.financial_year: {
                'fy': fy,
                'periods': list(fy.periods.all())
            }
            for fy in FinancialYear.objects.all()
        }
        fy_int, period_int = int(
            self.fy_and_period[:4]), int(self.fy_and_period[4:])
        while(other):
            if(other > period_int):
                fy_int = fy_int - 1
                if fy_int in fys:
                    other = other - period_int
                    period_int = int(fys[fy_int]["periods"][-1].period)
                else:
                    raise MissingPeriodError(
                        "Previous FY with periods is missing")
            elif other == period_int:
                fy_int = fy_int - 1
                if fy_int in fys:
                    return fys[fy_int]["periods"][-1]
                else:
                    raise MissingPeriodError(
                        "Previous FY with periods is missing")
            else:
                return fys[fy_int]["periods"][(period_int - 1) - other]

    def __le__(self, other):
        return int(self.fy_and_period) <= int(other.fy_and_period)

    def __lt__(self, other):
        return int(self.fy_and_period) < int(other.fy_and_period)

    def __ge__(self, other):
        return int(self.fy_and_period) >= int(other.fy_and_period)

    def __gt__(self, other):
        return int(self.fy_and_period) > int(other.fy_and_period)

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

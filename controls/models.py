from accountancy.mixins import AuditMixin
from django.db import models

from controls.exceptions import MissingFinancialYear, MissingPeriodError
from controls.validators import is_fy_year


class ModuleSettings(AuditMixin, models.Model):
    """
    This model should only ever have 1 record.

    Whenever transactions are affected - either create, edit, void - we provide the user with a period range based on
    the period of the module as set in this model's single record.

    The form constrains the period for each module so that a period cannot be chosen which is in a FY already finalised.
    """
    cash_book_period = models.ForeignKey(
        "Period", verbose_name="Cash Book Period", on_delete=models.SET_NULL, null=True, related_name="cash_book_period")
    nominals_period = models.ForeignKey(
        "Period", verbose_name="Nominals Period", on_delete=models.SET_NULL, null=True, related_name="nominals_period")
    purchases_period = models.ForeignKey(
        "Period", verbose_name="Purchases Period", on_delete=models.SET_NULL, null=True, related_name="purchases_period")
    sales_period = models.ForeignKey(
        "Period", verbose_name="Sales Period", on_delete=models.SET_NULL, null=True, related_name="sales_period")

    def module_periods(self):
        return {
            "cash_book_period": self.cash_book_period,
            "nominals_period": self.nominals_period,
            "purchases_period": self.purchases_period,
            "sales_period": self.sales_period
        }

# When / if i come to do a UI audit for this i may need to remove AuditMixin
class FinancialYear(AuditMixin, models.Model):
    financial_year = models.PositiveSmallIntegerField(
        validators=[is_fy_year], unique=True)
    number_of_periods = models.PositiveIntegerField(default=12)

    class Meta:
        ordering = ['financial_year']

    def __str__(self):
        return str(self.financial_year)

    def first_period(self):
        periods = self.periods.all()
        if periods:
            return periods[0]
        raise MissingPeriodError("No periods found for this year")

    def next_fy(self):
        next_fy = self.financial_year + 1
        try:
            return FinancialYear.objects.get(financial_year=next_fy)
        except FinancialYear.DoesNotExist:
            raise MissingFinancialYear(f"FY {next_fy} does not exist.")


class Period(AuditMixin, models.Model):
    period = models.CharField(max_length=2)
    fy_and_period = models.CharField(max_length=6, null=True)
    month_start = models.DateField()
    # CharField is better than SmallIntegerField because often we'll need to split into year and period
    # e.g. 202001, which is the first period of FY 2020, would need spliting into 2020, 01 for business logic
    fy = models.ForeignKey(
        FinancialYear, on_delete=models.SET_NULL, null=True, related_name="periods")

    class Meta:
        ordering = ['fy_and_period']

    @property
    def fys(self):
        if hasattr(self, '_fys'):
            fys = self._fys
        else:
            fys = {
                fy.financial_year: {
                    'fy': fy,
                    'periods': list(fy.periods.all())
                }
                for fy in FinancialYear.objects.all().prefetch_related('periods')
            }
            self._fys = fys # cache
        return fys

    def __add__(self, other):
        fys = self.fys
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
        fys = self.fys
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
            return self.fy_and_period[4:] + " " + self.fy_and_period[:4]
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

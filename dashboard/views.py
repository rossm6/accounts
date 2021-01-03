from cashbook.models import CashBookTransaction
from controls.models import ModuleSettings, Period
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.views.generic import TemplateView
from purchases.models import PurchaseHeader, PurchaseMatching
from sales.models import SaleHeader, SaleMatching


class TotalOwedReport:
    def __init__(self, header_model, match_model):
        self.header_model = header_model
        self.match_model = match_model

    def _report(self, matched_by, matched_to, types, period_subquery):
        return (
            self.header_model
            .objects
            .filter(type__in=types)
            .filter(period__fy_and_period__in=Subquery(period_subquery))
            .annotate(
                mbt=Coalesce(
                    Subquery(
                        matched_by.values('matched_by_total')
                    ),
                    0
                )
            )
            .annotate(
                mtt=Coalesce(
                    Subquery(
                        matched_to.values('matched_to_total')
                    ),
                    0
                )
            )
            .annotate(
                actual_due=F('due') + F('mbt') + F('mtt')
            )

        )

    def _report_per_period_for_last_5_periods(self, matched_by, matched_to, types, period):
        period_subquery = (
            Period
            .objects
            .filter(fy_and_period__lte=period.fy_and_period)
            .values('fy_and_period')
            .order_by("-fy_and_period")
            [:5]
        )
        q = (
            self
            ._report(matched_by, matched_to, types, period_subquery)
            .values('period__fy_and_period')
            .annotate(
                total_due=Coalesce(Sum('actual_due'), 0)
            )
        )
        report = {}
        for period in period_subquery:
            report[period["fy_and_period"]] = 0
        for period in q:
            report[period["period__fy_and_period"]] = period["total_due"]
        return report


    def _report_for_all_periods_prior(self, matched_by, matched_to, types, period):
        """
        Get the total owed for all periods prior to @period i.e. the total for 'Older'
        """
        period_subquery = (
            Period
            .objects
            .filter(fy_and_period__lte=period.fy_and_period)
            .values('fy_and_period')
            .order_by("-fy_and_period")
            [5:]
        )
        return (
            self
            ._report(matched_by, matched_to, types, period_subquery)
            .aggregate(
                total_due=Coalesce(Sum('actual_due'), 0)
            )
        )

    def report(self, current_period):
        """
        This is used by the dashboard and not the aged creditors report
        """
        matched_by = (
            self.match_model
            .objects
            .filter(period__fy_and_period__gt=current_period.fy_and_period)
            .filter(matched_by=OuterRef('pk'))
            .values('matched_by')
            .annotate(matched_by_total=Sum('value') * -1)
        )
        matched_to = (
            self.match_model
            .objects
            .filter(period__fy_and_period__gt=current_period.fy_and_period)
            .filter(matched_to=OuterRef('pk'))
            .values('matched_to')
            .annotate(matched_to_total=Sum('value'))
        )
        non_payment_types = [
            t[0]
            for t in self.header_model.types
            if t[0] not in self.header_model.payment_types
        ]
        report_from_current_to_4_periods_ago = self._report_per_period_for_last_5_periods(
            matched_by, matched_to, non_payment_types, current_period)
        older = self._report_for_all_periods_prior(
            matched_by, matched_to, non_payment_types, current_period)
        report = []
        labels = ["Current", "1 period ago", "2 periods ago", "3 periods ago", "4 periods ago"]
        for i, (period, value) in enumerate(report_from_current_to_4_periods_ago.items()):
            r = {
                "period": labels[i],
                "value": value
            }
            report.append(r)
        report.append({
            "period": "Older",
            "value": older["total_due"]
        })
        report.reverse() # In UI we actually want 'Older' to show first from left to right i.e. opposite of list
        return report


class DashBoard(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mod_settings = ModuleSettings.objects.first()
        cash_book_period = mod_settings.cash_book_period
        cash_book_in_and_out_report = (
            CashBookTransaction
            .objects
            .cash_book_in_and_out_report(cash_book_period)
        )
        cash_book_in_and_out = []
        for period in cash_book_in_and_out_report:
            p = period["period__fy_and_period"]
            o = {}
            o["period"] = p[4:] + " " + p[:4]
            o["in"] = period["total_monies_in"]
            o["out"] = period["total_monies_out"]
            cash_book_in_and_out.append(o)
        context["cash_in_and_out"] = cash_book_in_and_out
        owed_to_you = TotalOwedReport(
            SaleHeader, SaleMatching).report(mod_settings.sales_period)
        owed_by_you = TotalOwedReport(PurchaseHeader, PurchaseMatching).report(
            mod_settings.purchases_period)
        context["owed_to_you"] = owed_to_you
        context["owed_by_you"] = owed_by_you
        return context

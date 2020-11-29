from django.db.models import Q
from itertools import groupby

from .models import PurchaseHeader, PurchaseMatching


def creditors(period):
    headers = PurchaseHeader.objects.filter(period__fy_and_period__lte=period.fy_and_period).order_by("pk")

    matches = (PurchaseMatching.objects
               .filter(period__fy_and_period__gt=period.fy_and_period)
               .filter(
                   Q(matched_by__in=headers) | Q(matched_to__in=headers)
               ))

    matches_for_header = {}
    for match in matches:
        if match.matched_by_id not in matches_for_header:
            matches_for_header[match.matched_by_id] = []
        matches_for_header[match.matched_by_id].append(match)
        if match.matched_to_id not in matches_for_header:
            matches_for_header[match.matched_to_id] = []
        matches_for_header[match.matched_to_id].append(match)

    for header in headers:
        if header.pk in matches_for_header:
            for match in matches_for_header[header.pk]:
                if match.matched_to == header:
                    header.due += match.value
                else:
                    header.due -= match.value

    return [header for header in headers if header.due != 0]

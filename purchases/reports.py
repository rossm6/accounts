from django.db.models import Q

from .models import PurchaseHeader, PurchaseMatching


def creditors():
    period = '202001'
    headers = PurchaseHeader.objects.filter(period__lte=period)
    matches = PurchaseMatching.objects
    .filter(period__lte=period)
    .filter(
        Q(matched_by__in=headers) | Q(matched_to__in=headers)
    )

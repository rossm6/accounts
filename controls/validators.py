from django import forms
from django.utils.translation import ugettext_lazy as _


def is_fy_year(value):
    if value < 2015 or value > 2030:
        raise forms.ValidationError(
            _(
                "Financial years must be between 2015 and 2030"
            ),
            code="invalid-year"
        )

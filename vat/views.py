from django.contrib.postgres.search import TrigramSimilarity
from django.http import JsonResponse
from django.views.generic import ListView

from vat.models import Vat


class LoadVatCodes(ListView):
    paginate_by = 50
    model = Vat

    def get_model(self):
        return self.model

    def get_queryset(self):
        if q := self.request.GET.get('q'):
            return (
                self.get_model().objects.annotate(
                    similarity=TrigramSimilarity('code', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return self.get_model().objects.all()

    def render_to_response(self, context, **response_kwargs):
        vats = []
        for vat in context["page_obj"].object_list:
            v = {
                "rate": vat.rate,
                'code': vat.code,
                "id": vat.id
            }
            vats.append(v)
        data = {"data": vats}
        return JsonResponse(data)

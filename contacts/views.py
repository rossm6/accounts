from itertools import chain

from accountancy.helpers import get_all_historical_changes
from accountancy.mixins import SingleObjectAuditDetailViewMixin
from accountancy.views import (JQueryDataTableMixin,
                               get_trig_vectors_for_different_inputs)
from crispy_forms.utils import render_crispy_form
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import TrigramSimilarity
from django.forms import inlineformset_factory
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView, ListView,
                                  UpdateView, View)
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from purchases.models import Supplier
from querystring_parser import parser
from sales.models import Customer

from contacts.forms import ContactForm, ModalContactForm
from contacts.models import Contact


class LoadContacts(ListView):
    """
    Purchases and Sales both use this for selecting either a supplier or customer via ajax / selectize widget.
    """
    paginate_by = 50

    def get_queryset(self):
        if q := self.request.GET.get('q'):
            return (
                self.model.objects.annotate(
                    similarity=TrigramSimilarity('code', q),
                ).filter(similarity__gt=0.3).order_by('-similarity')
            )
        return self.model.objects.none()

    def render_to_response(self, context, **response_kwargs):
        contacts = []
        for contact in context["page_obj"].object_list:
            s = {
                'code': contact.code,
                "id": contact.id
            }
            contacts.append(s)
        data = {"data": contacts}
        return JsonResponse(data)


class ContactListView(LoginRequiredMixin, JQueryDataTableMixin, TemplateResponseMixin, View):
    model = Contact
    template_name = "contacts/contact_list.html"
    searchable_fields = ['code', 'name', 'email']
    columns = searchable_fields

    def get_row_href(self, obj):
        return reverse_lazy("contacts:detail", kwargs={"pk": obj.pk})

    def get_queryset(self):
        queryset_filter = self.request.GET.get("q")
        if queryset_filter == "customers":
            return self.model.objects.filter(customer=True)
        elif queryset_filter == "suppliers":
            return self.model.objects.filter(supplier=True)
        else:
            return self.model.objects.all()

    def load_page(self, **kwargs):
        context = super().load_page(**kwargs)
        queryset_filter = self.request.GET.get("q")
        if queryset_filter == "customers":
            contact_filter = "customers"
        elif queryset_filter == "suppliers":
            contact_filter = "suppliers"
        else:
            contact_filter = "all"
        context["contact_filter"] = contact_filter
        context["counts"] = {
            "customers": self.model.objects.filter(customer=True).count(),
            "suppliers": self.model.objects.filter(supplier=True).count(),
            "all": self.model.objects.all().count()
        }
        return context


class CreateAndUpdateMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        return context


class CreateContact(LoginRequiredMixin, CreateAndUpdateMixin, CreateView):
    model = Contact
    form_class = ContactForm
    ajax_form_class = ModalContactForm
    template_name = "contacts/contact_create_and_edit.html"
    prefix = "contact"
    success_url = reverse_lazy("contacts:list")
    title = "Create Contact"

    def get_form_class(self):
        if self.request.is_ajax():
            return self.ajax_form_class
        return self.form_class

    def form_valid(self, form):
        redirect_response = super().form_valid(form)
        if self.request.is_ajax():
            data = {}
            new_contact = self.object
            data["new_object"] = {
                "id": new_contact.pk,
                "code": str(new_contact),
            }
            data["success"] = True
            return JsonResponse(data=data)
        return redirect_response

    def render_to_response(self, context, **response_kwargs):
        # form is not valid
        if self.request.is_ajax():
            ctx = {}
            ctx.update(csrf(self.request))
            form = context["form"]
            form_html = render_crispy_form(form, context=ctx)
            data = {
                "form_html": form_html,
                "success": False
            }
            return JsonResponse(data=data)
        return super().render_to_response(context, **response_kwargs)


class ContactDetail(LoginRequiredMixin, SingleObjectAuditDetailViewMixin, DetailView):
    model = Contact
    template_name = "contacts/contact_detail.html"
    context_object_name = "contact"


class ContactUpdate(LoginRequiredMixin, CreateAndUpdateMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "contacts/contact_create_and_edit.html"
    context_object_name = "contact"
    success_url = reverse_lazy("contacts:list")
    title = "Edit Contact"

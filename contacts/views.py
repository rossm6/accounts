from contacts.models import Contact
from itertools import chain

from accountancy.views import (get_trig_vectors_for_different_inputs,
                               jQueryDataTable)
from crispy_forms.utils import render_crispy_form
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import inlineformset_factory
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView,
                                  UpdateView, View)
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from purchases.models import Supplier
from querystring_parser import parser
from sales.models import Customer
from utils.helpers import get_all_historical_changes
from contacts.forms import ContactForm, ModalContactForm


class ContactListView(LoginRequiredMixin, jQueryDataTable, TemplateResponseMixin, View):
    model = Contact
    template_name = "contacts/contact_list.html"
    searchable_fields = ['code', 'name', 'email']

    def get_model(self):
        return self.model

    def get(self, request, *args, **kwargs):
        if request.is_ajax():
            # populate the table
            context = self.get_context_for_ajax_request(**kwargs)
            # need the recordsTotal i.e. not considering search
            querysets = self.get_querysets()
            counts = self.get_total_counts(querysets)
            q_filter = self.request.GET.get("q")
            if q_filter == "customer":
                recordsTotal = counts["customer"]
            elif q_filter == "supplier":
                recordsTotal = counts["supplier"]
            else:
                recordsTotal = counts["all"]
            data = {
                "draw": int(self.request.GET.get("draw"), 0),
                "recordsTotal": recordsTotal,
                "recordsFiltered": context["paginator_object"].count,
                "data": context["data"]
            }
            return JsonResponse(data=data, safe=False)
        else:
            page_load_context = self.get_page_load_context_data(**kwargs)
            return self.render_to_response(page_load_context)

    def apply_search(self, queryset):
        parsed_request = parser.parse(self.request.GET.urlencode())
        if search_value := parsed_request["search"]["value"]:
            queryset = queryset.annotate(
                similarity=(
                    get_trig_vectors_for_different_inputs([
                        (field, search_value, )
                        for field in self.searchable_fields
                    ])
                )
            ).filter(similarity__gt=0.5)
        return queryset

    def get_querysets(self):
        customers = self.get_model().objects.filter(customer=True)
        suppliers = self.get_model().objects.filter(supplier=True)
        return {
            "customer": customers,
            "supplier": suppliers,
            "all": self.get_model().objects.all()
        }

    def get_total_counts(self, querysets):
        counts = {}
        for q in querysets:
            copy_queryset = querysets[q].all()
            counts[q] = copy_queryset.count()
        return counts

    def get_page_load_context_data(self, **kwargs):
        context = {}
        querysets = self.get_querysets()
        q_filter = self.request.GET.get("q")
        if q_filter == "customer":
            context["contact_filter"] = "customer"
        elif q_filter == "supplier":
            context["contact_filter"] = "supplier"
        else:
            context["contact_filter"] = "all"
        # for the nav bar
        counts = self.get_total_counts(querysets)
        context["counts"] = counts
        return context

    def get_context_for_ajax_request(self, **kwargs):
        context = {}
        querysets = self.get_querysets()
        q_filter = self.request.GET.get("q")
        if q_filter == 'customer':
            q = querysets["customer"]
            q = self.apply_search(q)
            contacts = q.order_by(*self.order_by())
        elif q_filter == 'supplier':
            q = querysets["supplier"]
            q = self.apply_search(q)
            contacts = q.order_by(*self.order_by())
        else:
            q = querysets["all"]
            q = self.apply_search(q)
            contacts = q.order_by(*self.order_by())

        paginator_object, page_object = self.paginate_objects(contacts)
        rows = []
        for contact in page_object.object_list:
            o = {
                "code": contact.code,
                "name": contact.name,
                "email": contact.email
            }
            pk = contact.pk
            href = reverse_lazy(
                "contacts:detail", kwargs={"pk": pk})
            o["DT_RowData"] = {
                "pk": pk,
                "href": href
            }
            rows.append(o)
        context["paginator_object"] = paginator_object
        context["data"] = rows
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


class ContactDetail(LoginRequiredMixin, DetailView):
    model = Contact
    template_name = "contacts/contact_detail.html"
    context_object_name = "contact"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = context["contact"]
        context["edit_href"] = reverse_lazy("contacts:edit", kwargs={
                                            "pk": instance.pk})
        audit_records = self.model.history.filter(
            **{
                self.model._meta.pk.name: instance.pk
            }
        ).order_by("pk")
        changes = get_all_historical_changes(audit_records)
        context["audits"] = changes
        return context


class ContactUpdate(LoginRequiredMixin, CreateAndUpdateMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "contacts/contact_create_and_edit.html"
    context_object_name = "contact"
    success_url = reverse_lazy("contacts:list")
    title = "Edit Contact"
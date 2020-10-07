from itertools import chain

from crispy_forms.utils import render_crispy_form
from django.forms import inlineformset_factory
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DeleteView, DetailView,
                                  UpdateView, View)
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from querystring_parser import parser

from accountancy.views import (get_trig_vectors_for_different_inputs,
                               jQueryDataTable)
from purchases.forms import ModalSupplierForm, SupplierForm
from purchases.models import Supplier
from sales.forms import CustomerForm
from sales.models import Customer
from utils.helpers import get_all_historical_changes


class ContactListView(jQueryDataTable, TemplateResponseMixin, View):
    customer_model = Customer
    supplier_model = Supplier
    template_name = "contacts/contact_list.html"
    searchable_fields = ['code', 'name', 'email']

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
                recordsTotal = counts["customer"] + counts["supplier"]
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
        customers = self.customer_model.objects.all()
        suppliers = self.supplier_model.objects.all()
        return {
            "customer": customers,
            "supplier": suppliers
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
        counts["all"] = sum([counts[c] for c in counts])
        context["counts"] = counts
        # get the form
        # to do
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
            # may be the fields common to both models ought to be
            # in a common sql table
            # at the moment they are not so we need to order in python
            querysets["customer"] = self.apply_search(querysets["customer"])
            querysets["supplier"] = self.apply_search(querysets["supplier"])
            contacts = list(
                chain(
                    *[list(querysets[q]) for q in querysets]
                )
            )
            contacts = self.order_objects(contacts, type="instance")
        paginator_object, page_object = self.paginate_objects(contacts)

        rows = []
        for contact in page_object.object_list:
            o = {
                "code": contact.code,
                "name": contact.name,
                "email": contact.email
            }
            if contact.__class__.__name__ == "Customer":
                pk = contact.pk
                href = reverse_lazy(
                    "contacts:customer_detail", kwargs={"pk": pk})
            else:
                pk = contact.pk
                href = reverse_lazy(
                    "contacts:supplier_detail", kwargs={"pk": pk})
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


class ContactCreateMixin:

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


class CreateCustomer(ContactCreateMixin, CreateAndUpdateMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "contacts/contact_create_and_edit.html"
    prefix = "customer"
    success_url = reverse_lazy("contacts:contact_list")
    title = "Create Customer"


class CreateSupplier(ContactCreateMixin, CreateAndUpdateMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    ajax_form_class = ModalSupplierForm
    template_name = "contacts/contact_create_and_edit.html"
    prefix = "supplier"
    title = "Create Supplier"
    success_url = reverse_lazy("contacts:contact_list")

class CustomerDetail(DetailView):
    model = Customer
    template_name = "contacts/contact_detail.html"
    context_object_name = "contact"
    edit_url_name = "edit_customer"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = context["contact"]
        context["edit_href"] = reverse_lazy("contacts:" + self.edit_url_name, kwargs={
                                            "pk": instance.pk})
        audit_records = self.model.history.filter(
            **{
                Customer._meta.pk.name: instance.pk
            }
        ).order_by("pk")
        changes = get_all_historical_changes(audit_records)
        context["audits"] = changes
        return context


class SupplierDetail(CustomerDetail):
    model = Supplier
    edit_url_name = "edit_supplier"


class CustomerUpdate(CreateAndUpdateMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "contacts/contact_create_and_edit.html"
    context_object_name = "contact"
    success_url = reverse_lazy("contacts:contact_list")
    title = "Edit Contact"


class SupplierUpdate(CustomerUpdate):
    model = Supplier
    form_class = SupplierForm

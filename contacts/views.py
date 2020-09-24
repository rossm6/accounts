from itertools import chain

from django.forms import inlineformset_factory
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView, View, DeleteView
from django.views.generic.base import ContextMixin, TemplateResponseMixin

from accountancy.views import jQueryDataTable
from purchases.models import Supplier
from sales.forms import CustomerForm
from sales.models import Customer


class ContactListView(jQueryDataTable, TemplateResponseMixin, View):
    customer_model = Customer
    supplier_model = Supplier
    template_name = "contacts/contact_list.html"

    def get(self, request, *args, **kwargs):
        if request.is_ajax():
            # populate the table
            context = self.get_context_for_ajax_request(**kwargs)
            data = {
                "draw": int(self.request.GET.get("draw"), 0),
                "recordsTotal": context["paginator_object"].count,
                # NOT CORRECT WHEN
                "recordsFiltered": context["paginator_object"].count,
                # SEARCH FORM IS IMPLEMENTED
                "data": context["data"]
            }
            return JsonResponse(data=data, safe=False)
        else:
            page_load_context = self.get_page_load_context_data(**kwargs)
            return self.render_to_response(page_load_context)

    def get_querysets(self):
        customers = self.customer_model.objects.all()
        suppliers = self.supplier_model.objects.all()
        return {
            "customers": customers,
            "suppliers": suppliers
        }

    def get_page_load_context_data(self, **kwargs):
        context = {}
        querysets = self.get_querysets()
        if "customer" in self.request.GET:
            context["contact_filter"] = "customer"
        elif "supplier" in self.request.GET:
            context["contact_filter"] = "supplier"
        else:
            context["contact_filter"] = "all"
        counts = {}
        # get the counts for the side navbar
        for q in querysets:
            copy_queryset = querysets[q].all()
            counts[q] = copy_queryset.count()
            # leave the original queryset as yet uneval'd
        counts["all"] = sum([counts[c] for c in counts])
        context["counts"] = counts
        # get the form
        # to do
        return context

    def get_context_for_ajax_request(self, **kwargs):
        context = {}
        querysets = self.get_querysets()
        if 'customers' in self.request.GET:
            contacts = querysets["customers"].order_by(*self.order_by())
        elif 'suppliers' in self.request.GET:
            contacts = querysets["suppliers"].order_by(*self.order_by())
        else:
            # may be the fields common to both models ought to be
            # in a common sql table
            # at the moment they are not so we need to order in python
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


class CreateCustomer(CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "contacts/contact_create.html"
    prefix = "customer"
    success_url = reverse_lazy("contacts:contact_list")


class CustomerDetail(DetailView):
    model = Customer
    template_name = "contacts/contact_detail.html"
    context_object_name = "contact"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["edit_href"] = reverse_lazy("contacts:edit_customer", kwargs={
                                            "pk": context["contact"].pk})
        return context


class SupplierDetail(CustomerDetail):
    model = Supplier


class CustomerUpdate(UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "contacts/contact_create.html"
    context_object_name = "contact"
    success_url = reverse_lazy("contacts:contact_list")

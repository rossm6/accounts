from django.urls import path

from .views import (CashBookCreate, CashBookDetail, CashBookEdit, CashBookList,
                    CreateTransaction, EditTransaction, TransactionEnquiry,
                    ViewTransaction, VoidTransaction)

app_name = "cashbook"
urlpatterns = [
    path("create", CreateTransaction.as_view(), name="create"),
    path("edit/<int:pk>", EditTransaction.as_view(), name="edit"),
    path("view/<int:pk>", ViewTransaction.as_view(), name="view"),
    path("void", VoidTransaction.as_view(), name="void"),
    path("transactions", TransactionEnquiry.as_view(), name="transaction_enquiry"),

    path("cashbook_create", CashBookCreate.as_view(), name="cashbook_create"),
    path("cashbook_list", CashBookList.as_view(), name="cashbook_list"),
    path("cashbook_detail/<int:pk>",
         CashBookDetail.as_view(), name="cashbook_detail"),
    path("cashbook_edit/<int:pk>", CashBookEdit.as_view(), name="cashbook_edit"),
]

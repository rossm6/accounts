from django.contrib.auth.mixins import PermissionRequiredMixin, PermissionDenied

class TransactionPermissionMixin(PermissionRequiredMixin):
    """
    Mixin has to come last in MRO because logic is based on transaction type
    """

    def get_permission_required(self):
        type_display = None
        header_model = self.get_header_model()
        if not hasattr(self, 'main_header'):
            # user therefore seeks to create a transactio
            if self.request.method == "POST":
                type_code = self.request.POST.get("header-type")
            else:
                type_code = self.get_header_form_type()
            for code, display in header_model.types:
                if code == type_code:
                    type_display = display
                    break
        else:
            type_display = self.main_header.get_type_display()
        if type_display:
            t = type_display.replace(" ", "_")
            t = t.lower()
            perm_required = f"{header_model._meta.app_label}.{self.permission_action}_{t}_transaction"
            return (perm_required,)
        raise PermissionDenied("Trying to access an unrecognised transaction type is not allowed")
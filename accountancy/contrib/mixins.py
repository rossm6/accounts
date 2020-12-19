from django.contrib.auth.mixins import PermissionRequiredMixin

class TransactionPermissionMixin(PermissionRequiredMixin):
    """
    Mixin has to come last in MRO because logic is based on transaction type
    """

    def get_permission_required(self):
        header_model = self.get_header_model()
        if not hasattr(self, 'main_header'):
            # user therefore seeks to create a transaction
            type_code = self.get_header_form_type()
            for code, display in header_model.types:
                if code == type_code:
                    type_display = display
                    break
        else:
            type_display = self.main_header.get_type_display()
        t = type_display.replace(" ", "_")
        t = t.lower()
        perm_required = f"{header_model._meta.app_label}.{self.permission_action}_{t}_transaction"
        return (perm_required,)
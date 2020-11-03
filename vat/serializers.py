def vat_object_for_input_dropdown_widget(obj):
    return {
        "id": obj.id,
        "text": str(obj),
        "rate": obj.rate
    }

from rest_framework import serializers

from .models import Nominal

class NominalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nominal
        fields = ['name', 'parent']
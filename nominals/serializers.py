from rest_framework import serializers

from .models import Nominal, NominalTransaction


class NominalSerializer(serializers.HyperlinkedModelSerializer):
    parent = serializers.HyperlinkedRelatedField(
        queryset=Nominal.objects.all(),
        view_name='nominals:nominal-detail',
        allow_null=True
    )

    class Meta:
        model = Nominal
        fields = ['name', 'parent']


class NominalTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominalTransaction
        fields = ['id', 'module', 'header', 'line', 'value', 'ref',
                  'period', 'date', 'field', 'nominal', 'type']

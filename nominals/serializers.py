from rest_framework import serializers

from .models import Nominal, NominalHeader, NominalLine, NominalTransaction


class NominalSerializer(serializers.HyperlinkedModelSerializer):
    parent = serializers.HyperlinkedRelatedField(
        queryset=Nominal.objects.all(),
        view_name='nominals:nominal-detail',
        allow_null=True
    )

    class Meta:
        model = Nominal
        fields = ['name', 'parent']


class NominalHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominalHeader
        fields = ['id', 'ref', 'goods', 'vat', 'total',
                  'date', 'period', 'status', 'type']


class NominalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominalLine
        fields = ['id', 'line_no', 'description', 'goods',
                  'vat', 'nominal', 'vat_code', 'goods_nominal_transaction', 'vat_nominal_transaction']


class NominalTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominalTransaction
        fields = ['id', 'module', 'header', 'line', 'value', 'ref',
                  'period', 'date', 'field', 'nominal', 'type']

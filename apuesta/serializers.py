from rest_framework import serializers

from apuesta.models import Apuesta
from apuesta.servicios import crear_apuesta_simple


class ApuestaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Apuesta
        fields = [
            'id_apuesta',
            'tipo_apuesta',
            'stake',
            'odds_total',
            'payout_potencial',
            'estado_apuesta',
            'aceptada_en',
            'liquidada_en',
            'created_at',
        ]


class CrearApuestaSimpleSerializer(serializers.Serializer):
    seleccion_id = serializers.IntegerField()
    stake = serializers.DecimalField(max_digits=18, decimal_places=4)
    idempotency_key = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        request = self.context['request']
        return crear_apuesta_simple(
            usuario=request.user,
            seleccion_id=validated_data['seleccion_id'],
            stake=validated_data['stake'],
            idempotency_key=validated_data.get('idempotency_key') or None,
        )

    def to_representation(self, instance):
        return ApuestaSerializer(instance).data

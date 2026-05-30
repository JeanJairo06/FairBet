from rest_framework import serializers

from apuesta.models import Apuesta
from apuesta.servicios import crear_apuesta_simple
from deporte.exceptions import OddsNoDisponibleError
from deporte.models import SeleccionMercado
from deporte.services.catalogo_service import obtener_odds_vigente


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
    # Versión de odds que el cliente vio al abrir el ticket.
    # Si difiere de la vigente se devuelve HTTP 409 con la nueva cuota.
    version_odds_esperada = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        version_esperada = attrs.get('version_odds_esperada')
        if version_esperada is None:
            return attrs

        seleccion_id = attrs.get('seleccion_id')
        try:
            seleccion = SeleccionMercado.objects.get(pk=seleccion_id)
            odds_vigente = obtener_odds_vigente(seleccion)
        except (SeleccionMercado.DoesNotExist, OddsNoDisponibleError):
            return attrs

        if odds_vigente.numero_version != version_esperada:
            raise serializers.ValidationError(
                {
                    'requiere_reconfirmacion': True,
                    'nueva_odds': str(odds_vigente.odds),
                    'nueva_version': odds_vigente.numero_version,
                    'detail': 'La cuota cambió. Confirma la nueva cuota para continuar.',
                }
            )
        return attrs

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

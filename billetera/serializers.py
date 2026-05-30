from rest_framework import serializers

from billetera.models import LedgerEntry, TransaccionLedger
from billetera.services.wallet_service import recargar_fichas, retirar_fichas


class SaldoSerializer(serializers.Serializer):
    saldo = serializers.DecimalField(max_digits=18, decimal_places=4)


class OperacionWalletSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=18, decimal_places=4)
    idempotency_key = serializers.CharField(max_length=120)


class RecargaSerializer(OperacionWalletSerializer):
    def create(self, validated_data):
        request = self.context['request']
        return recargar_fichas(
            usuario=request.user,
            monto=validated_data['monto'],
            idempotency_key=validated_data['idempotency_key'],
        )


class RetiroSerializer(OperacionWalletSerializer):
    def create(self, validated_data):
        request = self.context['request']
        return retirar_fichas(
            usuario=request.user,
            monto=validated_data['monto'],
            idempotency_key=validated_data['idempotency_key'],
        )


class OperacionWalletResponseSerializer(serializers.ModelSerializer):
    monto = serializers.SerializerMethodField()

    class Meta:
        model = TransaccionLedger
        fields = [
            'transaction_id',
            'tipo_transaccion',
            'estado',
            'idempotency_key',
            'monto',
            'created_at',
        ]

    def get_monto(self, obj):
        entry = obj.entries.filter(cuenta__usuario=obj.usuario).first()
        return entry.amount if entry else None


class LedgerEntrySerializer(serializers.ModelSerializer):
    transaction_id = serializers.UUIDField(source='transaccion.transaction_id', read_only=True)
    tipo_transaccion = serializers.CharField(source='transaccion.tipo_transaccion', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            'id_ledger_entry',
            'transaction_id',
            'tipo_transaccion',
            'direction',
            'amount',
            'created_at',
        ]


class TransaccionEntrySerializer(serializers.ModelSerializer):
    cuenta = serializers.CharField(source='cuenta.codigo', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ['cuenta', 'direction', 'amount', 'created_at']


class TransaccionLedgerSerializer(serializers.ModelSerializer):
    entries = serializers.SerializerMethodField()

    class Meta:
        model = TransaccionLedger
        fields = [
            'transaction_id',
            'tipo_transaccion',
            'estado',
            'idempotency_key',
            'tipo_referencia',
            'id_referencia',
            'metadata_json',
            'created_at',
            'entries',
        ]

    def get_entries(self, obj):
        request = self.context.get('request')
        entries = obj.entries.select_related('cuenta')
        if request and not request.user.is_staff:
            entries = entries.filter(cuenta__usuario=request.user)
        return TransaccionEntrySerializer(entries, many=True).data

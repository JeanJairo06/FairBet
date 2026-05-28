from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from billetera.exceptions import (
    CuentaBloqueadaError,
    CuentaNoEncontradaError,
    MontoInvalidoError,
    SaldoInsuficienteError,
    TransaccionNoBalanceadaError,
)
from billetera.models import LedgerEntry, TransaccionLedger
from billetera.serializers import (
    LedgerEntrySerializer,
    OperacionWalletResponseSerializer,
    RecargaSerializer,
    RetiroSerializer,
    SaldoSerializer,
    TransaccionLedgerSerializer,
)
from billetera.services.account_service import obtener_cuenta_wallet
from billetera.services.balance_service import calcular_saldo_usuario


def _error_response(exc):
    if isinstance(exc, CuentaNoEncontradaError):
        return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

    if isinstance(
        exc,
        (CuentaBloqueadaError, MontoInvalidoError, SaldoInsuficienteError, TransaccionNoBalanceadaError),
    ):
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    raise exc


class SaldoView(APIView):
    @extend_schema(responses={200: SaldoSerializer})
    def get(self, request):
        try:
            saldo = calcular_saldo_usuario(request.user)
        except Exception as exc:
            return _error_response(exc)

        serializer = SaldoSerializer({'saldo': saldo})
        return Response(serializer.data)


class RecargaView(APIView):
    @extend_schema(
        request=RecargaSerializer,
        responses={201: OperacionWalletResponseSerializer},
    )
    def post(self, request):
        serializer = RecargaSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        try:
            transaccion = serializer.save()
        except Exception as exc:
            return _error_response(exc)

        response_serializer = OperacionWalletResponseSerializer(transaccion)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class RetiroView(APIView):
    @extend_schema(
        request=RetiroSerializer,
        responses={201: OperacionWalletResponseSerializer},
    )
    def post(self, request):
        serializer = RetiroSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        try:
            transaccion = serializer.save()
        except Exception as exc:
            return _error_response(exc)

        response_serializer = OperacionWalletResponseSerializer(transaccion)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MovimientoListView(ListAPIView):
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        cuenta = obtener_cuenta_wallet(self.request.user)
        return (
            LedgerEntry.objects.filter(cuenta=cuenta)
            .select_related('transaccion')
            .order_by('-created_at')
        )


class TransaccionDetailView(RetrieveAPIView):
    serializer_class = TransaccionLedgerSerializer
    lookup_field = 'transaction_id'
    lookup_url_kwarg = 'transaction_id'

    def get_queryset(self):
        return (
            TransaccionLedger.objects.filter(usuario=self.request.user)
            .prefetch_related('entries__cuenta')
            .order_by('-created_at')
        )

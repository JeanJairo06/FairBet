from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from billetera.models import Cuenta, LedgerEntry, TransaccionLedger
from core.choices import DirectionLedger, TipoCuentaContable, TipoTransaccionLedger


class BilleteraModelTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='wallet_user',
            email='wallet_user@test.com',
            password='test12345',
        )

    def test_crea_cuenta_wallet_de_usuario(self):
        cuenta = Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-USER-1',
            nombre='Wallet usuario 1',
        )

        self.assertEqual(cuenta.usuario, self.usuario)
        self.assertEqual(cuenta.tipo_cuenta, TipoCuentaContable.WALLET_USUARIO)

    def test_wallet_usuario_requiere_usuario(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cuenta.objects.create(
                    tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
                    codigo='WALLET-SIN-USUARIO',
                    nombre='Wallet sin usuario',
                )

    def test_usuario_no_puede_tener_dos_wallets(self):
        Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-UNICA-1',
            nombre='Wallet unica 1',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cuenta.objects.create(
                    usuario=self.usuario,
                    tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
                    codigo='WALLET-UNICA-2',
                    nombre='Wallet unica 2',
                )

    def test_cuentas_internas_no_deben_tener_usuario(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cuenta.objects.create(
                    usuario=self.usuario,
                    tipo_cuenta=TipoCuentaContable.CASA,
                    codigo='CASA-CON-USUARIO',
                    nombre='Casa con usuario',
                )

    def test_crea_transaccion_ledger_y_entries(self):
        wallet = Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-ENTRY-1',
            nombre='Wallet entry 1',
        )
        casa = Cuenta.objects.create(
            tipo_cuenta=TipoCuentaContable.CASA,
            codigo='CASA-ENTRY-1',
            nombre='Casa entry 1',
        )
        transaccion_ledger = TransaccionLedger.objects.create(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            idempotency_key='recarga-entry-1',
        )

        LedgerEntry.objects.create(
            transaccion=transaccion_ledger,
            cuenta=wallet,
            amount=Decimal('100.0000'),
            direction=DirectionLedger.CREDIT,
        )
        LedgerEntry.objects.create(
            transaccion=transaccion_ledger,
            cuenta=casa,
            amount=Decimal('100.0000'),
            direction=DirectionLedger.DEBIT,
        )

        self.assertEqual(transaccion_ledger.entries.count(), 2)

    def test_ledger_entry_rechaza_monto_no_positivo(self):
        wallet = Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-AMOUNT-1',
            nombre='Wallet amount 1',
        )
        transaccion_ledger = TransaccionLedger.objects.create(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            idempotency_key='recarga-amount-1',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LedgerEntry.objects.create(
                    transaccion=transaccion_ledger,
                    cuenta=wallet,
                    amount=Decimal('0.0000'),
                    direction=DirectionLedger.CREDIT,
                )

    def test_transaccion_referencia_es_unica_por_tipo(self):
        TransaccionLedger.objects.create(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.BLOQUEO_APUESTA,
            tipo_referencia='apuesta',
            id_referencia='1',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransaccionLedger.objects.create(
                    usuario=self.usuario,
                    tipo_transaccion=TipoTransaccionLedger.BLOQUEO_APUESTA,
                    tipo_referencia='apuesta',
                    id_referencia='1',
                )

        TransaccionLedger.objects.create(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.LIQUIDACION,
            tipo_referencia='apuesta',
            id_referencia='1',
        )

        self.assertEqual(TransaccionLedger.objects.count(), 2)

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from billetera.models import Cuenta, LedgerEntry, TransaccionLedger
from billetera.exceptions import (
    CuentaBloqueadaError,
    CuentaNoEncontradaError,
    MontoInvalidoError,
    SaldoInsuficienteError,
    TransaccionNoBalanceadaError,
)
from billetera.services.balance_service import calcular_saldo, calcular_saldo_usuario, validar_saldo_suficiente
from billetera.services.account_service import (
    asegurar_cuentas_sistema,
    crear_cuenta_wallet_usuario,
    obtener_cuenta_sistema,
    obtener_cuenta_wallet,
    obtener_o_crear_cuenta_sistema,
)
from billetera.services.ledger_service import crear_transaccion_ledger, validar_transaccion_balanceada
from billetera.services.wallet_service import (
    bloquear_stake,
    liquidar_apuesta_ganada,
    liquidar_apuesta_perdida,
    liquidar_apuesta_void,
    recargar_fichas,
    retirar_fichas,
)
from core.choices import (
    DirectionLedger,
    EstadoCuentaContable,
    EstadoCuentaJugador,
    EstadoTransaccionLedger,
    PeriodoLimite,
    TipoCuentaContable,
    TipoTransaccionLedger,
)
from cuentas.models import PerfilJugador
from juego_responsable.models import LimiteJuegoResponsable


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


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='ledger_service_user',
            email='ledger_service_user@test.com',
            password='test12345',
        )
        self.wallet = Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-SERVICE-1',
            nombre='Wallet service 1',
        )
        self.casa = Cuenta.objects.create(
            tipo_cuenta=TipoCuentaContable.CASA,
            codigo='CASA-SERVICE-1',
            nombre='Casa service 1',
        )

    def entries_balanceados(self):
        return [
            {
                'cuenta': self.wallet,
                'direction': DirectionLedger.CREDIT,
                'amount': Decimal('100.0000'),
            },
            {
                'cuenta': self.casa,
                'direction': DirectionLedger.DEBIT,
                'amount': Decimal('100.0000'),
            },
        ]

    def test_crea_transaccion_balanceada_completada(self):
        transaccion_ledger = crear_transaccion_ledger(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            entries=self.entries_balanceados(),
            idempotency_key='service-recarga-1',
        )

        self.assertEqual(transaccion_ledger.estado, EstadoTransaccionLedger.COMPLETED)
        self.assertEqual(transaccion_ledger.entries.count(), 2)
        self.assertTrue(validar_transaccion_balanceada(transaccion_ledger))

    def test_rechaza_transaccion_sin_entries(self):
        with self.assertRaises(TransaccionNoBalanceadaError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=[],
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_rechaza_transaccion_con_un_solo_entry(self):
        with self.assertRaises(TransaccionNoBalanceadaError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=self.entries_balanceados()[:1],
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_rechaza_monto_cero(self):
        entries = self.entries_balanceados()
        entries[0]['amount'] = Decimal('0.0000')

        with self.assertRaises(MontoInvalidoError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=entries,
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_rechaza_monto_negativo(self):
        entries = self.entries_balanceados()
        entries[0]['amount'] = Decimal('-10.0000')

        with self.assertRaises(MontoInvalidoError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=entries,
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_rechaza_transaccion_desbalanceada(self):
        entries = self.entries_balanceados()
        entries[1]['amount'] = Decimal('90.0000')

        with self.assertRaises(TransaccionNoBalanceadaError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=entries,
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_rechaza_cuenta_no_activa(self):
        self.wallet.estado = EstadoCuentaContable.BLOQUEADA
        self.wallet.save(update_fields=['estado'])

        with self.assertRaises(CuentaBloqueadaError):
            crear_transaccion_ledger(
                usuario=self.usuario,
                tipo_transaccion=TipoTransaccionLedger.RECARGA,
                entries=self.entries_balanceados(),
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_reutiliza_transaccion_por_idempotency_key(self):
        primera = crear_transaccion_ledger(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            entries=self.entries_balanceados(),
            idempotency_key='service-idempotente-1',
        )
        segunda = crear_transaccion_ledger(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            entries=self.entries_balanceados(),
            idempotency_key='service-idempotente-1',
        )

        self.assertEqual(primera, segunda)
        self.assertEqual(TransaccionLedger.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 2)

    def test_crea_transaccion_con_metadata_y_referencia(self):
        transaccion_ledger = crear_transaccion_ledger(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.BLOQUEO_APUESTA,
            entries=self.entries_balanceados(),
            idempotency_key='service-metadata-1',
            tipo_referencia='apuesta',
            id_referencia=123,
            metadata={'origen': 'test'},
        )

        self.assertEqual(transaccion_ledger.tipo_referencia, 'apuesta')
        self.assertEqual(transaccion_ledger.id_referencia, '123')
        self.assertEqual(transaccion_ledger.metadata_json, {'origen': 'test'})

    def test_validar_transaccion_balanceada_existente_falla_si_no_tiene_entries(self):
        transaccion_ledger = TransaccionLedger.objects.create(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
        )

        with self.assertRaises(TransaccionNoBalanceadaError):
            validar_transaccion_balanceada(transaccion_ledger)


class BalanceServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='balance_user',
            email='balance_user@test.com',
            password='test12345',
        )
        self.otro_usuario = get_user_model().objects.create_user(
            username='balance_user_sin_wallet',
            email='balance_user_sin_wallet@test.com',
            password='test12345',
        )
        self.wallet = Cuenta.objects.create(
            usuario=self.usuario,
            tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            codigo='WALLET-BALANCE-1',
            nombre='Wallet balance 1',
        )
        self.casa = Cuenta.objects.create(
            tipo_cuenta=TipoCuentaContable.CASA,
            codigo='CASA-BALANCE-1',
            nombre='Casa balance 1',
        )

    def crear_movimiento_balanceado(self, wallet_direction, casa_direction, amount, idempotency_key):
        return crear_transaccion_ledger(
            usuario=self.usuario,
            tipo_transaccion=TipoTransaccionLedger.TRANSFERENCIA,
            entries=[
                {
                    'cuenta': self.wallet,
                    'direction': wallet_direction,
                    'amount': amount,
                },
                {
                    'cuenta': self.casa,
                    'direction': casa_direction,
                    'amount': amount,
                },
            ],
            idempotency_key=idempotency_key,
        )

    def test_calcular_saldo_sin_movimientos_devuelve_cero(self):
        self.assertEqual(calcular_saldo(self.wallet), Decimal('0.0000'))

    def test_calcular_saldo_con_creditos_y_debitos(self):
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.CREDIT,
            casa_direction=DirectionLedger.DEBIT,
            amount=Decimal('100.0000'),
            idempotency_key='balance-credit-1',
        )
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.DEBIT,
            casa_direction=DirectionLedger.CREDIT,
            amount=Decimal('30.0000'),
            idempotency_key='balance-debit-1',
        )
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.CREDIT,
            casa_direction=DirectionLedger.DEBIT,
            amount=Decimal('20.0000'),
            idempotency_key='balance-credit-2',
        )

        self.assertEqual(calcular_saldo(self.wallet), Decimal('90.0000'))

    def test_calcular_saldo_usuario_usa_wallet(self):
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.CREDIT,
            casa_direction=DirectionLedger.DEBIT,
            amount=Decimal('50.0000'),
            idempotency_key='balance-user-1',
        )

        self.assertEqual(calcular_saldo_usuario(self.usuario), Decimal('50.0000'))

    def test_calcular_saldo_usuario_falla_si_no_tiene_wallet(self):
        with self.assertRaises(CuentaNoEncontradaError):
            calcular_saldo_usuario(self.otro_usuario)

    def test_validar_saldo_suficiente_ok(self):
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.CREDIT,
            casa_direction=DirectionLedger.DEBIT,
            amount=Decimal('80.0000'),
            idempotency_key='balance-suficiente-1',
        )

        self.assertTrue(validar_saldo_suficiente(self.wallet, Decimal('60.0000')))

    def test_validar_saldo_suficiente_falla(self):
        self.crear_movimiento_balanceado(
            wallet_direction=DirectionLedger.CREDIT,
            casa_direction=DirectionLedger.DEBIT,
            amount=Decimal('40.0000'),
            idempotency_key='balance-insuficiente-1',
        )

        with self.assertRaises(SaldoInsuficienteError):
            validar_saldo_suficiente(self.wallet, Decimal('60.0000'))

    def test_validar_saldo_suficiente_rechaza_monto_cero(self):
        with self.assertRaises(MontoInvalidoError):
            validar_saldo_suficiente(self.wallet, Decimal('0.0000'))

    def test_validar_saldo_suficiente_rechaza_monto_negativo(self):
        with self.assertRaises(MontoInvalidoError):
            validar_saldo_suficiente(self.wallet, Decimal('-1.0000'))


class AccountServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='account_service_user',
            email='account_service_user@test.com',
            password='test12345',
        )

    def test_crear_cuenta_wallet_usuario(self):
        cuenta = crear_cuenta_wallet_usuario(self.usuario)

        self.assertEqual(cuenta.usuario, self.usuario)
        self.assertEqual(cuenta.tipo_cuenta, TipoCuentaContable.WALLET_USUARIO)
        self.assertEqual(cuenta.codigo, f'WALLET-USUARIO-{self.usuario.pk}')

    def test_crear_cuenta_wallet_usuario_es_idempotente(self):
        primera = crear_cuenta_wallet_usuario(self.usuario)
        segunda = crear_cuenta_wallet_usuario(self.usuario)

        self.assertEqual(primera, segunda)
        self.assertEqual(
            Cuenta.objects.filter(usuario=self.usuario, tipo_cuenta=TipoCuentaContable.WALLET_USUARIO).count(),
            1,
        )

    def test_obtener_cuenta_wallet_existente(self):
        cuenta = crear_cuenta_wallet_usuario(self.usuario)

        self.assertEqual(obtener_cuenta_wallet(self.usuario), cuenta)

    def test_obtener_cuenta_wallet_falla_si_no_existe(self):
        with self.assertRaises(CuentaNoEncontradaError):
            obtener_cuenta_wallet(self.usuario)

    def test_obtener_o_crear_cuenta_sistema_casa(self):
        cuenta = obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)

        self.assertIsNone(cuenta.usuario)
        self.assertEqual(cuenta.tipo_cuenta, TipoCuentaContable.CASA)
        self.assertEqual(cuenta.codigo, 'SISTEMA-CASA')

    def test_obtener_o_crear_cuenta_sistema_es_idempotente(self):
        primera = obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        segunda = obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)

        self.assertEqual(primera, segunda)
        self.assertEqual(
            Cuenta.objects.filter(tipo_cuenta=TipoCuentaContable.APUESTAS_PENDIENTES, usuario=None).count(),
            1,
        )

    def test_obtener_o_crear_cuenta_sistema_rechaza_wallet_usuario(self):
        with self.assertRaises(ValueError):
            obtener_o_crear_cuenta_sistema(TipoCuentaContable.WALLET_USUARIO)

    def test_obtener_cuenta_sistema_existente(self):
        cuenta = obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)

        self.assertEqual(obtener_cuenta_sistema(TipoCuentaContable.CASA), cuenta)

    def test_obtener_cuenta_sistema_falla_si_no_existe(self):
        with self.assertRaises(CuentaNoEncontradaError):
            obtener_cuenta_sistema(TipoCuentaContable.CASA)

    def test_asegurar_cuentas_sistema_crea_cuentas_base(self):
        cuentas = asegurar_cuentas_sistema()

        self.assertEqual(
            set(cuentas.keys()),
            {TipoCuentaContable.CASA, TipoCuentaContable.APUESTAS_PENDIENTES, TipoCuentaContable.BONOS},
        )
        self.assertEqual(Cuenta.objects.filter(usuario=None).count(), 3)


class WalletServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='wallet_service_user',
            email='wallet_service_user@test.com',
            password='test12345',
        )
        self.wallet = crear_cuenta_wallet_usuario(self.usuario)
        self.casa = obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        self.apuestas_pendientes = obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)

    def test_recargar_fichas_aumenta_saldo(self):
        transaccion = recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='recarga-wallet-1')

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.RECARGA)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('100.0000'))
        self.assertEqual(calcular_saldo(self.casa), Decimal('-100.0000'))

    def test_recargar_fichas_crea_entries_correctos(self):
        transaccion = recargar_fichas(self.usuario, Decimal('75.0000'), idempotency_key='recarga-wallet-entries')

        wallet_entry = transaccion.entries.get(cuenta=self.wallet)
        casa_entry = transaccion.entries.get(cuenta=self.casa)

        self.assertEqual(wallet_entry.direction, DirectionLedger.CREDIT)
        self.assertEqual(wallet_entry.amount, Decimal('75.0000'))
        self.assertEqual(casa_entry.direction, DirectionLedger.DEBIT)
        self.assertEqual(casa_entry.amount, Decimal('75.0000'))
        self.assertEqual(transaccion.idempotency_key, 'recarga-recarga-wallet-entries')
        self.assertEqual(transaccion.metadata_json, {'operacion': 'recarga', 'monto': '75.0000'})

    def test_recargar_fichas_es_idempotente(self):
        primera = recargar_fichas(self.usuario, Decimal('50.0000'), idempotency_key='recarga-idempotente')
        segunda = recargar_fichas(self.usuario, Decimal('50.0000'), idempotency_key='recarga-idempotente')

        self.assertEqual(primera, segunda)
        self.assertEqual(TransaccionLedger.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 2)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('50.0000'))

    def test_recargar_fichas_rechaza_monto_negativo(self):
        with self.assertRaises(MontoInvalidoError):
            recargar_fichas(self.usuario, Decimal('-10.0000'), idempotency_key='recarga-negativa')

        self.assertEqual(TransaccionLedger.objects.count(), 0)


    def test_retirar_fichas_disminuye_saldo(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='retiro-base-1')

        transaccion = retirar_fichas(self.usuario, Decimal('30.0000'), idempotency_key='retiro-wallet-1')

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.RETIRO)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('70.0000'))
        self.assertEqual(calcular_saldo(self.casa), Decimal('-70.0000'))

    def test_retirar_fichas_crea_entries_correctos(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='retiro-base-entries')

        transaccion = retirar_fichas(self.usuario, Decimal('40.0000'), idempotency_key='retiro-wallet-entries')
        wallet_entry = transaccion.entries.get(cuenta=self.wallet)
        casa_entry = transaccion.entries.get(cuenta=self.casa)

        self.assertEqual(wallet_entry.direction, DirectionLedger.DEBIT)
        self.assertEqual(wallet_entry.amount, Decimal('40.0000'))
        self.assertEqual(casa_entry.direction, DirectionLedger.CREDIT)
        self.assertEqual(casa_entry.amount, Decimal('40.0000'))
        self.assertEqual(transaccion.idempotency_key, 'retiro-retiro-wallet-entries')
        self.assertEqual(transaccion.metadata_json, {'operacion': 'retiro', 'monto': '40.0000'})

    def test_retirar_fichas_falla_sin_saldo(self):
        with self.assertRaises(SaldoInsuficienteError):
            retirar_fichas(self.usuario, Decimal('10.0000'), idempotency_key='retiro-sin-saldo')

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_retirar_fichas_es_idempotente(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='retiro-idempotente-base')

        primera = retirar_fichas(self.usuario, Decimal('80.0000'), idempotency_key='retiro-idempotente')
        segunda = retirar_fichas(self.usuario, Decimal('80.0000'), idempotency_key='retiro-idempotente')

        self.assertEqual(primera, segunda)
        self.assertEqual(TransaccionLedger.objects.count(), 2)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('20.0000'))

    def test_retirar_fichas_rechaza_monto_cero(self):
        with self.assertRaises(MontoInvalidoError):
            retirar_fichas(self.usuario, Decimal('0.0000'), idempotency_key='retiro-cero')

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_bloquear_stake_mueve_fondos_a_apuestas_pendientes(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='bloqueo-base-1')

        transaccion = bloquear_stake(self.usuario, apuesta_id=10, monto=Decimal('25.0000'), idempotency_key='bloqueo-1')

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.BLOQUEO_APUESTA)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('75.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('25.0000'))

    def test_bloquear_stake_crea_entries_correctos(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='bloqueo-base-entries')

        transaccion = bloquear_stake(self.usuario, apuesta_id=11, monto=Decimal('30.0000'), idempotency_key='bloqueo-entries')
        wallet_entry = transaccion.entries.get(cuenta=self.wallet)
        pendientes_entry = transaccion.entries.get(cuenta=self.apuestas_pendientes)

        self.assertEqual(wallet_entry.direction, DirectionLedger.DEBIT)
        self.assertEqual(wallet_entry.amount, Decimal('30.0000'))
        self.assertEqual(pendientes_entry.direction, DirectionLedger.CREDIT)
        self.assertEqual(pendientes_entry.amount, Decimal('30.0000'))
        self.assertEqual(transaccion.tipo_referencia, 'apuesta')
        self.assertEqual(transaccion.id_referencia, '11')
        self.assertEqual(transaccion.idempotency_key, 'bloqueo-apuesta-bloqueo-entries')
        self.assertEqual(transaccion.metadata_json, {'operacion': 'bloqueo_apuesta', 'apuesta_id': '11', 'monto': '30.0000'})

    def test_bloquear_stake_falla_sin_saldo(self):
        with self.assertRaises(SaldoInsuficienteError):
            bloquear_stake(self.usuario, apuesta_id=12, monto=Decimal('10.0000'), idempotency_key='bloqueo-sin-saldo')

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_bloquear_stake_es_idempotente(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='bloqueo-idempotente-base')

        primera = bloquear_stake(self.usuario, apuesta_id=13, monto=Decimal('80.0000'), idempotency_key='bloqueo-idempotente')
        segunda = bloquear_stake(self.usuario, apuesta_id=13, monto=Decimal('80.0000'), idempotency_key='bloqueo-idempotente')

        self.assertEqual(primera, segunda)
        self.assertEqual(TransaccionLedger.objects.count(), 2)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('20.0000'))

    def test_bloquear_stake_rechaza_monto_cero(self):
        with self.assertRaises(MontoInvalidoError):
            bloquear_stake(self.usuario, apuesta_id=14, monto=Decimal('0.0000'), idempotency_key='bloqueo-cero')

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_liquidar_apuesta_ganada_paga_payout(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='liquidacion-ganada-base')
        bloquear_stake(self.usuario, apuesta_id=20, monto=Decimal('20.0000'), idempotency_key='liquidacion-ganada-bloqueo')

        transaccion = liquidar_apuesta_ganada(
            self.usuario,
            apuesta_id=20,
            stake=Decimal('20.0000'),
            payout=Decimal('50.0000'),
            idempotency_key='liquidacion-ganada',
        )

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('130.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))
        self.assertEqual(calcular_saldo(self.casa), Decimal('-130.0000'))

    def test_liquidar_apuesta_ganada_crea_entries_correctos(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='liquidacion-ganada-entries-base')
        bloquear_stake(self.usuario, apuesta_id=21, monto=Decimal('20.0000'), idempotency_key='liquidacion-ganada-entries-bloqueo')

        transaccion = liquidar_apuesta_ganada(
            self.usuario,
            apuesta_id=21,
            stake=Decimal('20.0000'),
            payout=Decimal('50.0000'),
            idempotency_key='liquidacion-ganada-entries',
        )

        pendientes_entry = transaccion.entries.get(cuenta=self.apuestas_pendientes)
        casa_entry = transaccion.entries.get(cuenta=self.casa)
        wallet_entry = transaccion.entries.get(cuenta=self.wallet)

        self.assertEqual(pendientes_entry.direction, DirectionLedger.DEBIT)
        self.assertEqual(pendientes_entry.amount, Decimal('20.0000'))
        self.assertEqual(casa_entry.direction, DirectionLedger.DEBIT)
        self.assertEqual(casa_entry.amount, Decimal('30.0000'))
        self.assertEqual(wallet_entry.direction, DirectionLedger.CREDIT)
        self.assertEqual(wallet_entry.amount, Decimal('50.0000'))
        self.assertEqual(transaccion.tipo_referencia, 'apuesta')
        self.assertEqual(transaccion.id_referencia, '21')

    def test_liquidar_apuesta_ganada_rechaza_payout_menor_a_stake(self):
        with self.assertRaises(MontoInvalidoError):
            liquidar_apuesta_ganada(
                self.usuario,
                apuesta_id=22,
                stake=Decimal('20.0000'),
                payout=Decimal('10.0000'),
                idempotency_key='liquidacion-payout-invalido',
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_liquidar_apuesta_perdida_mueve_stake_a_casa(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='liquidacion-perdida-base')
        bloquear_stake(self.usuario, apuesta_id=23, monto=Decimal('20.0000'), idempotency_key='liquidacion-perdida-bloqueo')

        transaccion = liquidar_apuesta_perdida(
            self.usuario,
            apuesta_id=23,
            stake=Decimal('20.0000'),
            idempotency_key='liquidacion-perdida',
        )

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('80.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))
        self.assertEqual(calcular_saldo(self.casa), Decimal('-80.0000'))

    def test_liquidar_apuesta_void_devuelve_stake(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='liquidacion-void-base')
        bloquear_stake(self.usuario, apuesta_id=24, monto=Decimal('20.0000'), idempotency_key='liquidacion-void-bloqueo')

        transaccion = liquidar_apuesta_void(
            self.usuario,
            apuesta_id=24,
            stake=Decimal('20.0000'),
            idempotency_key='liquidacion-void',
        )

        self.assertEqual(transaccion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('100.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))
        self.assertEqual(calcular_saldo(self.casa), Decimal('-100.0000'))

    def test_liquidacion_es_idempotente(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='liquidacion-idempotente-base')
        bloquear_stake(self.usuario, apuesta_id=25, monto=Decimal('20.0000'), idempotency_key='liquidacion-idempotente-bloqueo')

        primera = liquidar_apuesta_perdida(
            self.usuario,
            apuesta_id=25,
            stake=Decimal('20.0000'),
            idempotency_key='liquidacion-idempotente',
        )
        segunda = liquidar_apuesta_perdida(
            self.usuario,
            apuesta_id=25,
            stake=Decimal('20.0000'),
            idempotency_key='liquidacion-idempotente',
        )

        self.assertEqual(primera, segunda)
        self.assertEqual(TransaccionLedger.objects.count(), 3)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('80.0000'))

    def test_liquidacion_rechaza_monto_cero(self):
        with self.assertRaises(MontoInvalidoError):
            liquidar_apuesta_perdida(
                self.usuario,
                apuesta_id=26,
                stake=Decimal('0.0000'),
                idempotency_key='liquidacion-cero',
            )

        self.assertEqual(TransaccionLedger.objects.count(), 0)


class BilleteraApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = get_user_model().objects.create_user(
            username='billetera_api_user',
            email='billetera_api_user@test.com',
            password='test12345',
        )
        self.otro_usuario = get_user_model().objects.create_user(
            username='billetera_api_otro',
            email='billetera_api_otro@test.com',
            password='test12345',
        )
        self.wallet = crear_cuenta_wallet_usuario(self.usuario)
        crear_cuenta_wallet_usuario(self.otro_usuario)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        self.client.force_authenticate(user=self.usuario)

    def test_api_consulta_saldo(self):
        recargar_fichas(self.usuario, Decimal('120.0000'), idempotency_key='api-saldo-base')

        response = self.client.get('/api/v1/billetera/saldo/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['saldo'], '120.0000')

    def test_api_saldo_falla_si_no_tiene_wallet(self):
        usuario_sin_wallet = get_user_model().objects.create_user(
            username='billetera_api_sin_wallet',
            email='billetera_api_sin_wallet@test.com',
            password='test12345',
        )
        self.client.force_authenticate(user=usuario_sin_wallet)

        response = self.client.get('/api/v1/billetera/saldo/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_recarga_fichas(self):
        response = self.client.post(
            '/api/v1/billetera/recargas/',
            {'monto': '100.0000', 'idempotency_key': 'api-recarga-1'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tipo_transaccion'], TipoTransaccionLedger.RECARGA)
        self.assertEqual(response.data['estado'], EstadoTransaccionLedger.COMPLETED)
        self.assertEqual(response.data['monto'], Decimal('100.0000'))
        self.assertEqual(calcular_saldo(self.wallet), Decimal('100.0000'))

    def test_api_recarga_idempotente(self):
        primera = self.client.post(
            '/api/v1/billetera/recargas/',
            {'monto': '50.0000', 'idempotency_key': 'api-recarga-idempotente'},
            format='json',
        )
        segunda = self.client.post(
            '/api/v1/billetera/recargas/',
            {'monto': '50.0000', 'idempotency_key': 'api-recarga-idempotente'},
            format='json',
        )

        self.assertEqual(primera.status_code, status.HTTP_201_CREATED)
        self.assertEqual(segunda.status_code, status.HTTP_201_CREATED)
        self.assertEqual(primera.data['transaction_id'], segunda.data['transaction_id'])
        self.assertEqual(calcular_saldo(self.wallet), Decimal('50.0000'))

    def test_api_retiro_fichas(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='api-retiro-base')

        response = self.client.post(
            '/api/v1/billetera/retiros/',
            {'monto': '40.0000', 'idempotency_key': 'api-retiro-1'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tipo_transaccion'], TipoTransaccionLedger.RETIRO)
        self.assertEqual(response.data['monto'], Decimal('40.0000'))
        self.assertEqual(calcular_saldo(self.wallet), Decimal('60.0000'))

    def test_api_retiro_falla_sin_saldo(self):
        response = self.client.post(
            '/api/v1/billetera/retiros/',
            {'monto': '40.0000', 'idempotency_key': 'api-retiro-sin-saldo'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TransaccionLedger.objects.count(), 0)

    def test_api_lista_movimientos_solo_del_usuario(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='api-movimientos-user')
        recargar_fichas(self.otro_usuario, Decimal('200.0000'), idempotency_key='api-movimientos-otro')

        response = self.client.get('/api/v1/billetera/movimientos/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['amount'], '100.0000')

    def test_api_detalle_transaccion_del_usuario(self):
        transaccion = recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='api-detalle-user')

        response = self.client.get(f'/api/v1/billetera/transacciones/{transaccion.transaction_id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['transaction_id'], str(transaccion.transaction_id))
        self.assertEqual(response.data['tipo_transaccion'], TipoTransaccionLedger.RECARGA)
        self.assertEqual(len(response.data['entries']), 1)
        self.assertEqual(response.data['entries'][0]['cuenta'], self.wallet.codigo)

    def test_api_no_permite_ver_transaccion_de_otro_usuario(self):
        transaccion = recargar_fichas(self.otro_usuario, Decimal('100.0000'), idempotency_key='api-detalle-otro')

        response = self.client.get(f'/api/v1/billetera/transacciones/{transaccion.transaction_id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BilleteraWebTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='billetera_web_user',
            email='billetera_web_user@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=self.usuario,
            nombres='Billetera',
            apellidos='Web',
            dni='72345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        self.wallet = crear_cuenta_wallet_usuario(self.usuario)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        self.client.force_login(self.usuario)

    def test_panel_billetera_muestra_saldo_historial_y_limites(self):
        recargar_fichas(self.usuario, Decimal('150.0000'), idempotency_key='web-panel-recarga')

        response = self.client.get('/billetera/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Billetera del jugador')
        self.assertEqual(response.context['saldo_disponible'], Decimal('150.0000'))
        self.assertContains(response, 'Historial de movimientos')
        self.assertContains(response, 'Limites de recarga')
        self.assertContains(response, 'Abrir Juego Responsable')
        self.assertContains(response, 'Gestionar autoexclusion')
        self.assertNotContains(response, 'Actualizar limites')

    def test_panel_billetera_recarga_con_servicios_existentes(self):
        response = self.client.post('/billetera/', {'accion': 'recargar', 'monto': '80.00'})

        self.assertRedirects(response, '/billetera/')
        self.assertEqual(calcular_saldo(self.wallet), Decimal('80.0000'))

    def test_panel_billetera_rechaza_recarga_sobre_limite(self):
        LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.DIARIO,
            limite_actual=Decimal('50.0000'),
        )

        response = self.client.post('/billetera/', {'accion': 'recargar', 'monto': '80.00'})

        self.assertRedirects(response, '/billetera/')
        self.assertEqual(calcular_saldo(self.wallet), Decimal('0.0000'))

    def test_panel_billetera_retiro_con_servicios_existentes(self):
        recargar_fichas(self.usuario, Decimal('100.0000'), idempotency_key='web-panel-retiro-base')

        response = self.client.post('/billetera/', {'accion': 'retirar', 'monto': '35.00'})

        self.assertRedirects(response, '/billetera/')
        self.assertEqual(calcular_saldo(self.wallet), Decimal('65.0000'))

    def test_panel_billetera_pagina_historial_de_a_10_registros(self):
        for indice in range(12):
            recargar_fichas(
                self.usuario,
                Decimal('1.0000'),
                idempotency_key=f'web-panel-paginacion-{indice}',
            )

        response = self.client.get('/billetera/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['movimientos']), 10)
        self.assertEqual(response.context['paginator'].count, 12)
        self.assertTrue(response.context['is_paginated'])

        segunda_pagina = self.client.get('/billetera/?page=2')

        self.assertEqual(segunda_pagina.status_code, 200)
        self.assertEqual(len(segunda_pagina.context['movimientos']), 2)

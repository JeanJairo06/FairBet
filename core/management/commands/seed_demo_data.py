from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billetera.services.account_service import crear_cuenta_wallet_usuario, obtener_o_crear_cuenta_sistema
from billetera.services.wallet_service import recargar_fichas
from core.choices import (
    EstadoCuentaJugador,
    EstadoEvento,
    EstadoMercado,
    EstadoSeleccion,
    PeriodoLimite,
    RolUsuario,
    TipoAutoexclusion,
    TipoCuentaContable,
    TipoMercado,
)
from cuentas.models import PerfilJugador
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado
from juego_responsable.models import Autoexclusion, LimiteJuegoResponsable


DEMO_PASSWORDS = {
    'admin': 'Admin12345!',
    'operador': 'Operador12345!',
    'jugador': 'Jugador12345!',
    'sin_saldo': 'Jugador12345!',
    'autoexcluido': 'Jugador12345!',
    'limite_bajo': 'Jugador12345!',
}


class Command(BaseCommand):
    help = 'Crea datos demo idempotentes para probar FairBet.'

    @transaction.atomic
    def handle(self, *args, **options):
        usuarios = self._crear_usuarios()
        self._crear_perfiles(usuarios)
        self._crear_juego_responsable(usuarios)
        self._crear_billetera(usuarios)
        self._crear_deportes(usuarios['operador'])

        self.stdout.write(self.style.SUCCESS('Datos demo creados correctamente.'))
        self.stdout.write('Credenciales:')
        for username, password in DEMO_PASSWORDS.items():
            self.stdout.write(f'  {username} / {password}')

    def _crear_usuarios(self):
        User = get_user_model()
        usuarios_config = {
            'admin': {
                'email': 'admin@fairbet.test',
                'rol': RolUsuario.ADMIN,
                'is_staff': True,
                'is_superuser': True,
            },
            'operador': {
                'email': 'operador@fairbet.test',
                'rol': RolUsuario.OPERATOR,
                'is_staff': True,
                'is_superuser': False,
            },
            'jugador': {
                'email': 'jugador@fairbet.test',
                'rol': RolUsuario.PLAYER,
                'is_staff': False,
                'is_superuser': False,
            },
            'sin_saldo': {
                'email': 'sin_saldo@fairbet.test',
                'rol': RolUsuario.PLAYER,
                'is_staff': False,
                'is_superuser': False,
            },
            'autoexcluido': {
                'email': 'autoexcluido@fairbet.test',
                'rol': RolUsuario.PLAYER,
                'is_staff': False,
                'is_superuser': False,
            },
            'limite_bajo': {
                'email': 'limite_bajo@fairbet.test',
                'rol': RolUsuario.PLAYER,
                'is_staff': False,
                'is_superuser': False,
            },
        }

        usuarios = {}
        for username, config in usuarios_config.items():
            usuario, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    'email': config['email'],
                    'rol': config['rol'],
                    'is_staff': config['is_staff'],
                    'is_superuser': config['is_superuser'],
                    'is_active': True,
                },
            )
            usuario.set_password(DEMO_PASSWORDS[username])
            usuario.save(update_fields=['password'])
            usuarios[username] = usuario

        return usuarios

    def _crear_perfiles(self, usuarios):
        perfiles = {
            'jugador': {
                'nombres': 'Jugador',
                'apellidos': 'Demo',
                'dni': '70000001',
                'estado_cuenta': EstadoCuentaJugador.VERIFICADO,
            },
            'sin_saldo': {
                'nombres': 'Jugador',
                'apellidos': 'Sin Saldo',
                'dni': '70000002',
                'estado_cuenta': EstadoCuentaJugador.VERIFICADO,
            },
            'autoexcluido': {
                'nombres': 'Jugador',
                'apellidos': 'Autoexcluido',
                'dni': '70000003',
                'estado_cuenta': EstadoCuentaJugador.AUTOEXCLUIDO,
            },
            'limite_bajo': {
                'nombres': 'Jugador',
                'apellidos': 'Limite Bajo',
                'dni': '70000004',
                'estado_cuenta': EstadoCuentaJugador.VERIFICADO,
            },
        }

        for username, data in perfiles.items():
            PerfilJugador.objects.update_or_create(
                usuario=usuarios[username],
                defaults={
                    **data,
                    'fecha_nacimiento': '2000-01-01',
                    'telefono': '999999999',
                    'kyc_verificado_en': timezone.now()
                    if data['estado_cuenta'] == EstadoCuentaJugador.VERIFICADO
                    else None,
                },
            )

    def _crear_juego_responsable(self, usuarios):
        limites_por_usuario = {
            'jugador': Decimal('1000.0000'),
            'sin_saldo': Decimal('1000.0000'),
            'autoexcluido': Decimal('1000.0000'),
            'limite_bajo': Decimal('20.0000'),
        }

        for username, limite in limites_por_usuario.items():
            for periodo in [PeriodoLimite.DIARIO, PeriodoLimite.SEMANAL, PeriodoLimite.MENSUAL]:
                LimiteJuegoResponsable.objects.update_or_create(
                    usuario=usuarios[username],
                    periodo=periodo,
                    defaults={
                        'limite_actual': limite,
                        'limite_pendiente': None,
                        'pendiente_aplicar_en': None,
                    },
                )

        Autoexclusion.objects.update_or_create(
            usuario=usuarios['autoexcluido'],
            activa=True,
            defaults={
                'tipo_autoexclusion': TipoAutoexclusion.TEMPORAL,
                'inicia_en': timezone.now(),
                'finaliza_en': timezone.now() + timezone.timedelta(days=30),
                'motivo': 'Datos demo: autoexclusion temporal activa.',
            },
        )

    def _crear_billetera(self, usuarios):
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.BONOS)

        for username in ['admin', 'operador', 'jugador', 'sin_saldo', 'autoexcluido', 'limite_bajo']:
            crear_cuenta_wallet_usuario(usuarios[username])

        recargas = {
            'admin': Decimal('100.0000'),
            'operador': Decimal('100.0000'),
            'jugador': Decimal('1000.0000'),
            'autoexcluido': Decimal('100.0000'),
            'limite_bajo': Decimal('20.0000'),
        }
        for username, monto in recargas.items():
            recargar_fichas(
                usuarios[username],
                monto,
                idempotency_key=f'seed-demo-recarga-{username}',
            )

    def _crear_deportes(self, operador):
        eventos = [
            {
                'deporte': 'Futbol',
                'competicion': 'Mundial 2026',
                'equipo_local': 'Peru',
                'equipo_visitante': 'Brasil',
                'inicia_en': timezone.now() + timezone.timedelta(days=7),
                'estado_evento': EstadoEvento.PROGRAMADO,
                'estado_mercado': EstadoMercado.ABIERTO,
            },
            {
                'deporte': 'Futbol',
                'competicion': 'Copa Demo',
                'equipo_local': 'Argentina',
                'equipo_visitante': 'Chile',
                'inicia_en': timezone.now() + timezone.timedelta(days=10),
                'estado_evento': EstadoEvento.PROGRAMADO,
                'estado_mercado': EstadoMercado.ABIERTO,
            },
            {
                'deporte': 'Futbol',
                'competicion': 'Liga Demo',
                'equipo_local': 'Colombia',
                'equipo_visitante': 'Uruguay',
                'inicia_en': timezone.now() + timezone.timedelta(days=5),
                'estado_evento': EstadoEvento.SUSPENDIDO,
                'estado_mercado': EstadoMercado.SUSPENDIDO,
            },
            {
                'deporte': 'Futbol',
                'competicion': 'Amistoso Demo',
                'equipo_local': 'Ecuador',
                'equipo_visitante': 'Bolivia',
                'inicia_en': timezone.now() - timezone.timedelta(days=1),
                'estado_evento': EstadoEvento.FINALIZADO,
                'estado_mercado': EstadoMercado.CERRADO,
            },
        ]

        for data in eventos:
            evento, _ = EventoDeportivo.objects.update_or_create(
                deporte=data['deporte'],
                competicion=data['competicion'],
                equipo_local=data['equipo_local'],
                equipo_visitante=data['equipo_visitante'],
                defaults={
                    'inicia_en': data['inicia_en'],
                    'estado_evento': data['estado_evento'],
                    'marcador_local': 0,
                    'marcador_visitante': 0,
                    'resultado_confirmado': data['estado_evento'] == EstadoEvento.FINALIZADO,
                },
            )
            mercado, _ = Mercado.objects.update_or_create(
                evento=evento,
                tipo_mercado=TipoMercado.UNO_X_DOS,
                nombre='Resultado final',
                defaults={
                    'estado_mercado': data['estado_mercado'],
                    'margen_operador': Decimal('0.0500'),
                    'stake_minimo': Decimal('5.0000'),
                    'stake_maximo': Decimal('100.0000'),
                    'permite_in_play': False,
                    'suspendido_hasta': None,
                },
            )
            self._crear_selecciones_y_odds(mercado, operador)

    def _crear_selecciones_y_odds(self, mercado, operador):
        selecciones = [
            ('HOME_WIN', 'Gana local', Decimal('2.5000')),
            ('DRAW', 'Empate', Decimal('3.1000')),
            ('AWAY_WIN', 'Gana visitante', Decimal('1.8000')),
        ]

        for codigo, nombre, odds in selecciones:
            seleccion, _ = SeleccionMercado.objects.update_or_create(
                mercado=mercado,
                codigo_seleccion=codigo,
                defaults={
                    'nombre': nombre,
                    'estado_seleccion': EstadoSeleccion.ACTIVA,
                },
            )
            HistorialOdds.objects.update_or_create(
                seleccion=seleccion,
                numero_version=1,
                defaults={
                    'odds': odds,
                    'activa': True,
                    'valido_desde': timezone.now(),
                    'valido_hasta': None,
                    'cambiado_por': operador,
                },
            )

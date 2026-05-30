from django.db.models.signals import post_save
from django.dispatch import receiver
from core.choices import EstadoCuentaJugador
from juego_responsable.models import Autoexclusion

@receiver(post_save, sender=Autoexclusion)
def activar_autoexclusion_en_perfil(sender, instance, created, **kwargs):

    if instance.activa and instance.esta_vigente():

        if hasattr(instance.usuario, 'perfil_jugador'):
            perfil = instance.usuario.perfil_jugador
            
            perfil.estado_cuenta = EstadoCuentaJugador.AUTOEXCLUIDO
            perfil.save()
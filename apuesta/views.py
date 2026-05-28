from rest_framework.generics import ListCreateAPIView

from apuesta.models import Apuesta
from apuesta.serializers import ApuestaSerializer, CrearApuestaSimpleSerializer


class ApuestaListCreateView(ListCreateAPIView):
    def get_queryset(self):
        return Apuesta.objects.filter(usuario=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CrearApuestaSimpleSerializer
        return ApuestaSerializer

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                'status': 'ok',
                'service': 'FairBet Lab API',
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            }
        )

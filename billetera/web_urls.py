from django.urls import path

from billetera.views.web_views import panel_billetera_view


app_name = 'billetera'

urlpatterns = [
    path('billetera/', panel_billetera_view, name='panel'),
]

from django.urls import path

from billetera.views import MovimientoListView, RecargaView, RetiroView, SaldoView, TransaccionDetailView


app_name = 'billetera'

urlpatterns = [
    path('billetera/saldo/', SaldoView.as_view(), name='saldo'),
    path('billetera/recargas/', RecargaView.as_view(), name='recargas'),
    path('billetera/retiros/', RetiroView.as_view(), name='retiros'),
    path('billetera/movimientos/', MovimientoListView.as_view(), name='movimientos'),
    path('billetera/transacciones/<uuid:transaction_id>/', TransaccionDetailView.as_view(), name='transaccion-detail'),
]

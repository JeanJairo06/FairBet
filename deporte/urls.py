from django.urls import path

from deporte import views

app_name = 'deporte'

urlpatterns = [
    path('', views.EventoListView.as_view(), name='eventos_lista'),
    path('eventos/nuevo/', views.EventoCreateView.as_view(), name='evento_crear'),
    path('eventos/<int:pk>/editar/', views.EventoUpdateView.as_view(), name='evento_editar'),
    path('eventos/<int:pk>/en-vivo/', views.EventoEstadoActionView.as_view(accion='en_vivo'), name='evento_en_vivo'),
    path('eventos/<int:pk>/suspender/', views.EventoEstadoActionView.as_view(accion='suspender'), name='evento_suspender'),
    path('eventos/<int:pk>/anular/', views.EventoEstadoActionView.as_view(accion='anular'), name='evento_anular'),
    path('eventos/<int:pk>/confirmar-resultado/', views.EventoConfirmarResultadoView.as_view(), name='evento_confirmar_resultado'),
    path('mercados/', views.MercadoListView.as_view(), name='mercados_lista'),
    path('mercados/nuevo/', views.MercadoCreateView.as_view(), name='mercado_crear'),
    path('mercados/<int:pk>/editar/', views.MercadoUpdateView.as_view(), name='mercado_editar'),
    path('selecciones/', views.SeleccionListView.as_view(), name='selecciones_lista'),
    path('selecciones/nueva/', views.SeleccionCreateView.as_view(), name='seleccion_crear'),
    path('selecciones/<int:pk>/editar/', views.SeleccionUpdateView.as_view(), name='seleccion_editar'),
    path('odds/', views.OddsListView.as_view(), name='odds_lista'),
    path('odds/actualizar/', views.OddsUpdateView.as_view(), name='odds_actualizar'),
]

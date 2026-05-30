from django.urls import path

from deporte import views

app_name = 'deporte'

urlpatterns = [
    path('', views.EventoListView.as_view(), name='eventos_lista'),
    path('eventos/nuevo/', views.EventoCreateView.as_view(), name='evento_crear'),
    path('partidos/<int:pk>/', views.EventoDetailView.as_view(), name='evento_detalle'),
    path('partidos/<int:pk>/mercados/rapido/', views.EventoMercadoRapidoView.as_view(), name='evento_mercado_rapido'),
    path('partidos/<int:pk>/mercados/personalizado/', views.EventoMercadoPersonalizadoView.as_view(), name='evento_mercado_personalizado'),
    path('partidos/<int:pk>/odds/actualizar/', views.EventoOddsActualizarView.as_view(), name='evento_odds_actualizar'),
    path('partidos/<int:pk>/mercados/<int:mercado_pk>/actualizar/', views.EventoMercadoOddsActualizarView.as_view(), name='evento_mercado_odds_actualizar'),
    path('eventos/<int:pk>/editar/', views.EventoUpdateView.as_view(), name='evento_editar'),
    path('eventos/<int:pk>/en-vivo/', views.EventoEstadoActionView.as_view(accion='en_vivo'), name='evento_en_vivo'),
    path('eventos/<int:pk>/reactivar/', views.EventoEstadoActionView.as_view(accion='reactivar'), name='evento_reactivar'),
    path('eventos/<int:pk>/suspender/', views.EventoEstadoActionView.as_view(accion='suspender'), name='evento_suspender'),
    path('eventos/<int:pk>/anular/', views.EventoEstadoActionView.as_view(accion='anular'), name='evento_anular'),
    path('eventos/<int:pk>/confirmar-resultado/', views.EventoConfirmarResultadoView.as_view(), name='evento_confirmar_resultado'),
    path('partidos/<int:pk>/marcador/', views.EventoMarcadorUpdateView.as_view(), name='evento_marcador_update'),
    path('odds/', views.OddsListView.as_view(), name='odds_lista'),
]

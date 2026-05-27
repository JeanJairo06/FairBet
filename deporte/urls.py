from django.urls import path

from deporte import views

app_name = 'deporte'

urlpatterns = [
    path('', views.EventoListView.as_view(), name='eventos_lista'),
    path('eventos/nuevo/', views.EventoCreateView.as_view(), name='evento_crear'),
    path('eventos/<int:pk>/editar/', views.EventoUpdateView.as_view(), name='evento_editar'),
    path('mercados/', views.MercadoListView.as_view(), name='mercados_lista'),
    path('mercados/nuevo/', views.MercadoCreateView.as_view(), name='mercado_crear'),
    path('mercados/<int:pk>/editar/', views.MercadoUpdateView.as_view(), name='mercado_editar'),
    path('selecciones/', views.SeleccionListView.as_view(), name='selecciones_lista'),
    path('selecciones/nueva/', views.SeleccionCreateView.as_view(), name='seleccion_crear'),
    path('selecciones/<int:pk>/editar/', views.SeleccionUpdateView.as_view(), name='seleccion_editar'),
    path('odds/', views.OddsListView.as_view(), name='odds_lista'),
    path('odds/actualizar/', views.OddsUpdateView.as_view(), name='odds_actualizar'),
]

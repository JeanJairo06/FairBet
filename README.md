# FairBet Lab

FairBet Lab es una plataforma educativa de apuestas deportivas con moneda virtual. El proyecto no integra pasarelas de pago reales, no convierte fichas a dinero y no constituye una casa de apuestas.

Disclaimer obligatorio: **Plataforma educativa con moneda virtual. No constituye una casa de apuestas.**

## Stack

- Python 3.11
- Django 5.x
- Django REST Framework
- SimpleJWT
- PostgreSQL
- Redis, Celery y Django Channels preparados para fases posteriores
- drf-spectacular para documentacion OpenAPI
- Docker y Docker Compose

## Reglas De Trabajo

- Todo el proyecto se ejecuta con Docker.
- No instalar dependencias directamente en el sistema local.
- No correr `python manage.py ...` localmente.
- Usar siempre `docker compose exec web ...` para comandos de Django.
- Trabajar siempre desde una rama propia.

## Entorno Virtual Local

El proyecto se ejecuta con Docker. El entorno virtual local solo puede usarse como apoyo del editor/IDE, no para levantar Django ni instalar dependencias de ejecucion.


Windows CMD:

```cmd
python -m venv venv
venv\Scripts\activate
```


## Clonar El Proyecto

```bash
git clone https://github.com/JeanJairo06/FairBet.git
cd FairBet
```

## Ubicarse En Una Rama

Si ya existe tu rama:

```bash
git fetch origin
git switch nombre-de-tu-rama
```

Si vas a crear una rama nueva:

```bash
git switch -c feature/nombre-de-tu-tarea
```

Ejemplos de nombres:

```bash
git switch -c feature/modelos-core
git switch -c feature/api-auth-jwt
git switch -c fix/settings-docker
```

## Configurar Variables De Entorno

Copiar el archivo de ejemplo:

Windows CMD:

```cmd
copy .env.example .env
```

Editar `.env` y completar como minimo:

```env
SECRET_KEY=django-insecure-cambia-este-valor
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=django.db.backends.postgresql
DB_NAME=fairbet_db
DB_USER=fairbet_user
DB_PASSWORD=fairbet_password
DB_HOST=db
DB_PORT=5432

CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

## Levantar El Proyecto Con Docker

Construir y levantar contenedores:

```bash
docker compose up -d --build
```

Verificar contenedores:

```bash
docker compose ps
```

Ver logs del servicio web:

```bash
docker compose logs -f web
```

## Ejecutar Migraciones

Todos los comandos de Django deben ejecutarse dentro del contenedor `web`.

```bash
docker compose exec web python manage.py migrate
```

Verificar que no haya errores de configuracion:

```bash
docker compose exec web python manage.py check
```

Verificar que no falten migraciones:

```bash
docker compose exec web python manage.py makemigrations --check --dry-run
```

## Crear Superusuario

```bash
docker compose exec web python manage.py createsuperuser
```

Luego ingresar al admin:

```text
http://localhost:8000/admin/
```

## API Actual

Base URL:

```text
http://localhost:8000/api/v1/
```

Rutas disponibles por ahora:

| Metodo | Ruta | Descripcion |
|---|---|---|
| POST | `/api/v1/auth/token/` | Obtener tokens JWT |
| POST | `/api/v1/auth/token/refresh/` | Renovar access token |
| GET | `/api/v1/docs/` | Swagger UI |
| GET | `/api/v1/schema/` | Schema OpenAPI |

Ejemplo para obtener token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"tu_password\"}"
```

Respuesta esperada:

```json
{
  "refresh": "eyJ...",
  "access": "eyJ..."
}
```

Para consumir endpoints protegidos en el futuro:

```http
Authorization: Bearer <access_token>
```

## Documentacion OpenAPI

Swagger UI:

```text
http://localhost:8000/api/v1/docs/
```

Schema OpenAPI:

```text
http://localhost:8000/api/v1/schema/
```

Validar schema desde Docker:

```bash
docker compose exec web python manage.py spectacular --validate
```

Exportar schema:

```bash
docker compose exec web python manage.py spectacular --file schema.yml
```

## Apps Del Proyecto

- `core`: choices, utilidades y clases base compartidas.
- `api`: rutas base, autenticacion JWT y documentacion OpenAPI.
- `cuentas`: usuarios, perfiles de jugador y KYC simulado.
- `juego_responsable`: limites de deposito virtual y autoexclusiones.
- `billetera`: cuentas contables, transacciones y ledger entries.
- `deporte`: eventos deportivos, mercados, selecciones y odds.
- `apuesta`: apuestas, detalles de apuesta y liquidaciones.
- `auditoria`: auditoria inmutable y trazabilidad.

## Modelos Principales

- `Usuario`
- `PerfilJugador`
- `LimiteJuegoResponsable`
- `Autoexclusion`
- `Cuenta`
- `TransaccionLedger`
- `LedgerEntry`
- `EventoDeportivo`
- `Mercado`
- `SeleccionMercado`
- `HistorialOdds`
- `Apuesta`
- `DetalleApuesta`
- `LiquidacionApuesta`
- `AuditoriaInmutable`

## Reglas Importantes Del Dominio

- Usar `Decimal`, nunca `float`, para montos, cuotas, stake y payout.
- El saldo no se almacena directamente; se deriva desde `LedgerEntry`.
- Toda operacion financiera debe crear debitos y creditos balanceados.
- Una apuesta aceptada debe tener fondos bloqueados en ledger.
- La autoexclusion bloquea apuestas y recargas.
- La auditoria debe ser append-only.

## Comandos Utiles

Apagar contenedores:

```bash
docker compose down
```

Apagar contenedores y eliminar volumenes de base de datos:

```bash
docker compose down -v
```

Reconstruir imagen:

```bash
docker compose build --no-cache
```

Abrir shell de Django:

```bash
docker compose exec web python manage.py shell
```

Crear migraciones despues de cambiar modelos:

```bash
docker compose exec web python manage.py makemigrations
```

Aplicar migraciones:

```bash
docker compose exec web python manage.py migrate
```

## Estado Actual

- Configuracion base de Django + DRF lista.
- JWT disponible en `/api/v1/auth/token/` y `/api/v1/auth/token/refresh/`.
- Documentacion OpenAPI disponible en `/api/v1/docs/` y `/api/v1/schema/`.
- Modelos del nucleo implementados.
- Modelos registrados en Django Admin.
- Migraciones iniciales generadas.

## Pendientes

- Servicios de billetera y ledger.
- Servicios de apuestas y liquidacion.
- Serializers y ViewSets del dominio.
- Tests de wallet, idempotencia y concurrencia.
- Vista o selector para saldos derivados.
- Seeds de eventos y usuarios.
- ADRs y documentacion de compliance.

# Git Workflow

Esta guia define el flujo de trabajo con Git para FairBet.

## Regla Principal

No trabajar directo en `main` ni en `develop`.

Cada cambio debe hacerse en una rama propia y luego enviarse mediante Pull Request hacia `develop`.

## Crear Una Rama Nueva

Primero actualizar `develop`:

```bash
git status
git checkout develop
git pull origin develop
```

Crear la rama de trabajo:

```bash
git checkout -b feature/nombre-de-su-rama
```

Ejemplos:

```bash
git checkout -b feature/api-auth-jwt
git checkout -b feature/modelos-billetera
git checkout -b fix/admin-modelos
```

## Nueva Funcionalidad

Revisar cambios:

```bash
git status
```

Agregar cambios:

```bash
git add .
```

Crear commit:

```bash
git commit -m "feat: implementar reservas"
```

Subir la rama:

```bash
git push origin feature/nombre-de-su-rama
```

Luego crear Pull Request en GitHub:

```text
feature/nombre-de-su-rama -> develop
```

## Actualizar Tu Rama Con Develop

Antes de seguir trabajando o antes de abrir un Pull Request, actualizar la rama con los ultimos cambios de `develop`.

```bash
git status
git checkout develop
git pull origin develop
git checkout feature/nombre-de-su-rama
git merge develop
git push origin feature/nombre-de-su-rama
```

## Si Aparece Un Conflicto

Resolver manualmente los archivos en conflicto.

Luego ejecutar:

```bash
git status
git add .
git commit -m "fix: resolver conflictos con develop"
git push origin feature/nombre-de-su-rama
```

## Convencion De Commits

Usar Conventional Commits:

```text
feat: nueva funcionalidad
fix: correccion de error
docs: cambios de documentacion
test: pruebas
refactor: refactorizacion sin cambiar comportamiento
chore: tareas de mantenimiento
```

Ejemplos:

```bash
git commit -m "feat: configurar jwt en api v1"
git commit -m "fix: corregir registro de modelos en admin"
git commit -m "docs: agregar guia de instalacion docker"
```

## Checklist Antes Del Pull Request

Ejecutar verificaciones dentro de Docker:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

Revisar estado final:

```bash
git status
```

El Pull Request debe apuntar a:

```text
develop
```

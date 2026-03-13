# Структура проекта (MVP)

## Каталоги

- `fluffychat/` - форк Flutter-клиента (приоритет Android)
- `synapse/` - форк Matrix Synapse
- `keygen/` - backend одноразовых токенов и QR (FastAPI)
- `infra/` - Docker Compose, конфиг nginx, infra-скрипты
- `docs/` - документация проекта и runbook-и

## Synapse

- Шаблон: `infra/synapse/homeserver.yaml.template`
- Рендер runtime-конфига: `infra/volumes/synapse/homeserver.yaml`
- Dev TLS-сертификаты: `infra/volumes/certs/dev.crt`, `infra/volumes/certs/dev.key`

## Keygen

- Код сервиса: `keygen/app.py`
- Docker-образ: `keygen/Dockerfile`
- API-контракт: `docs/keygen-api.md`
- Публичные маршруты через nginx:
- `POST /keygen/token/create`
- `POST /keygen/token/redeem`
- `GET /keygen/healthz`

## Сетевая топология

- Сеть `edge`: внешние порты есть только у `nginx`
- Сеть `internal`: `synapse`, `postgres`, `keygen`, `nginx`
- Прямой внешний доступ к `postgres` и `keygen` отсутствует

## Быстрые команды

Из корня репозитория:

```powershell
.\infra\scripts\dev.ps1 -Command init
.\infra\scripts\dev.ps1 -Command up
.\infra\scripts\dev.ps1 -Command ps
.\infra\scripts\dev.ps1 -Command logs -Service nginx
.\infra\scripts\dev.ps1 -Command down
```

Smoke-check Matrix API:

```powershell
curl.exe -sk https://localhost/_matrix/client/versions
```

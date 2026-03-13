# SecMess

SecMess - закрытый мессенджер на базе Matrix.

Текущий репозиторий содержит серверный контур MVP:
- `infra/` - Docker Compose, nginx, шаблоны конфигов и скрипты запуска
- `keygen/` - сервис одноразовых токенов/QR (FastAPI)
- `synapse/` - форк Matrix Synapse
- `docs/` - документация, runbook-и, инструкции по эксплуатации

Клиент `fluffychat/` может находиться рядом локально, но в корневой git не включён.

## Что реализовано в MVP

- Логин через одноразовые invite-токены (QR/token flow)
- Role-based доступ к админским операциям (`admin`, `super-admin`, `developer`)
- Защита админских endpoint-ов через master key
- Развёртывание всего серверного контура в Docker

## Быстрый старт (сервер)

1. Подготовь `.env`:
```bash
cp infra/.env.example infra/.env
```

2. Сгенерируй конфиг Synapse:
```bash
mkdir -p infra/volumes/postgres infra/volumes/synapse infra/volumes/certs
set -a
source infra/.env
set +a
envsubst < infra/synapse/homeserver.yaml.template > infra/volumes/synapse/homeserver.yaml
```

3. Подними стек:
```bash
cd infra
docker compose --env-file .env -f docker-compose.yml up -d --build
```

4. Проверка:
```bash
curl -sk https://localhost/healthz
curl -sk https://localhost/keygen/healthz
curl -sk https://localhost/_matrix/client/versions
```

## Полезные команды (PowerShell)

```powershell
.\infra\scripts\dev.ps1 -Command init
.\infra\scripts\dev.ps1 -Command up
.\infra\scripts\dev.ps1 -Command ps
.\infra\scripts\dev.ps1 -Command logs -Service nginx
.\infra\scripts\dev.ps1 -Command errors
.\infra\scripts\dev.ps1 -Command down
```

## Документация

- Развёртывание: [docs/deploy.md](docs/deploy.md)
- API keygen: [docs/keygen-api.md](docs/keygen-api.md)
- Админский runbook: [docs/admin.md](docs/admin.md)
- Сборка Android-клиента: [docs/client-build.md](docs/client-build.md)
- Бэкапы и восстановление: [docs/backup-restore.md](docs/backup-restore.md)
- Стратегия бэкапов: [docs/backup-strategy.md](docs/backup-strategy.md)
- Restore drill: [docs/restore-drill.md](docs/restore-drill.md)
- Безопасность VPS: [docs/security-hardening.md](docs/security-hardening.md)
- Структура проекта: [docs/structure.md](docs/structure.md)

## Важно по безопасности

- Не коммить секреты (`infra/.env`, ключи, сертификаты, runtime-данные томов).
- Перед публичным запуском проверь, что наружу открыт только `nginx` (порт `443`).
- Регулярно ротируй `KEYGEN_MASTER_KEY` и храни его офлайн.

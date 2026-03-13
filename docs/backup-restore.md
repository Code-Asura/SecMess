# Runbook по резервному копированию и восстановлению

Аварийная процедура восстановления SecMess после сбоя инфраструктуры.

Связанные документы:

1. `docs/backup-strategy.md`
2. `docs/restore-drill.md`

## 1) Критичный контур резервного копирования

1. База PostgreSQL (`synapse`)
2. `infra/.env`
3. `infra/volumes/synapse/` (медиа, ключи, состояние Synapse)
4. `infra/volumes/certs/`

## 2) Создание бэкапов (запускать из `infra/`)

### 2.1 Дамп PostgreSQL

```bash
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/postgres
docker compose --env-file .env -f docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "backups/postgres/postgres_${TS}.dump"
sha256sum "backups/postgres/postgres_${TS}.dump" > "backups/postgres/postgres_${TS}.dump.sha256"
```

### 2.2 Архив конфигов и томов

```bash
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/files
tar -czf "backups/files/files_${TS}.tar.gz" \
  .env \
  volumes/synapse \
  volumes/certs
sha256sum "backups/files/files_${TS}.tar.gz" > "backups/files/files_${TS}.tar.gz.sha256"
```

## 3) Восстановление (запускать из `infra/`)

### 3.1 Проверка контрольных сумм

```bash
sha256sum -c backups/postgres/postgres_<ts>.dump.sha256
sha256sum -c backups/files/files_<ts>.tar.gz.sha256
```

### 3.2 Остановка стека

```bash
docker compose --env-file .env -f docker-compose.yml down
```

### 3.3 Восстановление файлов

```bash
tar -xzf backups/files/files_<ts>.tar.gz -C .
```

### 3.4 Поднять Postgres и восстановить дамп

```bash
docker compose --env-file .env -f docker-compose.yml up -d postgres
cat backups/postgres/postgres_<ts>.dump | \
docker compose --env-file .env -f docker-compose.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges
```

### 3.5 Поднять все сервисы

```bash
docker compose --env-file .env -f docker-compose.yml up -d --build
docker compose --env-file .env -f docker-compose.yml ps
```

## 4) Проверка после восстановления

1. `curl -sk https://<domain>/healthz`
2. `curl -sk https://<domain>/keygen/healthz`
3. `curl -sk https://<domain>/_matrix/client/versions`
4. Вход из клиента и проверка чатов/медиа
5. Проверка ошибок сервисов:

```powershell
.\infra\scripts\dev.ps1 -Command errors
```

## 5) Что фиксировать в отчёте инцидента

1. Время инцидента
2. Время бэкапа, из которого шло восстановление
3. Фактические `RPO` и `RTO`
4. Объём потерь данных (если есть)
5. Какие улучшения внести в процесс резервирования

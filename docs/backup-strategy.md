# Стратегия резервного копирования SecMess (MVP)

Цель: обеспечить восстановление Matrix-контура после потери VPS или повреждения данных.

## 1. Что резервируем

1. PostgreSQL (`synapse` DB): пользователи, комнаты, события, метаданные E2EE.
2. Конфиги и секреты:
- `infra/.env`
- `infra/volumes/synapse/homeserver.yaml`
- TLS-сертификаты в `infra/volumes/certs/`
3. Данные Synapse:
- `/data/media_store`
- ключи подписи и прочие runtime-данные Synapse (`infra/volumes/synapse/` целиком).

## 2. Целевые показатели (MVP)

- `RPO`: до 6 часов.
- `RTO`: до 2 часов.

## 3. Периодичность

1. Дамп PostgreSQL: каждые 6 часов.
2. Архив Synapse volume + конфиги: 1 раз в сутки.
3. Внепланово: перед обновлением Docker-образов и перед миграциями.

## 4. Хранение и retention

1. Локально на VPS: 7 дней.
2. Внешнее хранилище (S3/Backblaze/другой сервер): 30 дней.
3. Минимум 1 недельная immutable-копия (WORM/Object Lock или readonly snapshot).

## 5. Контроль целостности

1. Для каждого архива сохраняй `sha256`.
2. Раз в неделю проверяй распаковку последнего полного бэкапа в тестовый каталог.
3. Раз в месяц выполняй полный restore drill по `docs/restore-drill.md`.

## 6. Пример команд (из `infra/`)

### 6.1 Дамп PostgreSQL

```bash
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/postgres
docker compose --env-file .env -f docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "backups/postgres/postgres_${TS}.dump"
sha256sum "backups/postgres/postgres_${TS}.dump" > "backups/postgres/postgres_${TS}.dump.sha256"
```

### 6.2 Архив Synapse + конфиги

```bash
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/files
tar -czf "backups/files/files_${TS}.tar.gz" \
  .env \
  volumes/synapse \
  volumes/certs
sha256sum "backups/files/files_${TS}.tar.gz" > "backups/files/files_${TS}.tar.gz.sha256"
```

## 7. Рекомендуемая автоматизация

1. `cron`/`systemd timer` для регулярного backup-job.
2. Отдельный upload-job во внешнее хранилище.
3. Алерт, если backup не создавался более 8 часов.

# Тренировочное восстановление SecMess (MVP)

Процедура учебного восстановления из бэкапа для `postgres + synapse + keygen + nginx`.

## 1. Подготовка

1. Выбери набор бэкапов:
- `backups/postgres/postgres_<ts>.dump`
- `backups/files/files_<ts>.tar.gz`
2. Проверь контрольные суммы:

```bash
sha256sum -c backups/postgres/postgres_<ts>.dump.sha256
sha256sum -c backups/files/files_<ts>.tar.gz.sha256
```

## 2. Остановка стека

Из каталога `infra/`:

```bash
docker compose --env-file .env -f docker-compose.yml down
```

## 3. Восстановление файлов

1. Очисти старые данные (только на test/drill-стенде).
2. Распакуй архив:

```bash
tar -xzf backups/files/files_<ts>.tar.gz -C .
```

После распаковки должны существовать:

- `.env`
- `volumes/synapse/`
- `volumes/certs/`

## 4. Подъём Postgres и восстановление БД

```bash
docker compose --env-file .env -f docker-compose.yml up -d postgres
```

Дождись статуса `healthy`, затем:

```bash
cat backups/postgres/postgres_<ts>.dump | \
docker compose --env-file .env -f docker-compose.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges
```

## 5. Полный подъём сервисов

```bash
docker compose --env-file .env -f docker-compose.yml up -d
docker compose --env-file .env -f docker-compose.yml ps
```

## 6. Проверка работоспособности

1. Health-эндпоинты:
- `GET /keygen/healthz`
- `GET /_matrix/client/versions`

2. Логи ошибок:

```powershell
.\scripts\dev.ps1 errors
```

3. Функциональная проверка:
- вход по токену в клиенте;
- отправка сообщения;
- загрузка и просмотр статичного изображения в чате.

## 7. Критерии успешного drill

1. Все контейнеры в статусе `Up`/`healthy`.
2. Пользователь может войти и видеть историю чатов.
3. Медиа из старых сообщений доступно.
4. `dev.ps1 errors` не показывает критических ошибок и crash-loop.

## 8. Отчёт после drill

Зафиксируй:

1. Дату и длительность восстановления (фактический RTO).
2. Возраст использованного бэкапа (фактический RPO).
3. Найденные проблемы и корректирующие действия.

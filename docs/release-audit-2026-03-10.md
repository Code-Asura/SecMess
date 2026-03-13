# Отчёт релизного аудита (2026-03-10)

## Область аудита

Проверены проектные части кода и инфраструктуры:

1. Backend `keygen`
2. Конфигурация `infra` (nginx/compose/env/скрипты)
3. Кастомизации SecMess в `fluffychat`
4. Документация и runbook-и по доставке/эксплуатации

## Исправленные замечания

### Критичные

1. Публично доступный Synapse admin path через nginx
- Исправлено: блокировка `/_synapse/` на edge (nginx).

2. Runtime-файлы Postgres фактически не были надёжно исключены из git
- Исправлено: правила `.gitignore` для игнорирования runtime-данных `infra/volumes/*`.

### Высокие

1. Поток генерации админского QR не всегда передавал обязательный master key header
- Добавлен запрос master key + безопасный in-memory cache в Flutter-flow.

2. QR-логин мог инициализировать клиент без `device_id` и падать в encryption init
- Добавлен fallback через `whoami` до `client.init(...)`.

3. Передача верификации ключей могла зависать в ожидании секрета
- Добавлено ограничение ожидания (`45s`) и явный timeout-сценарий.

### Средние

1. В keygen была слабая валидация JSON-ответов Synapse
- Добавлены проверки парсинга для nonce/register/whoami.

2. Параметр `ttl_seconds` был не полностью ограничен политикой max TTL
- Добавлена runtime-проверка относительно `KEYGEN_MAX_TTL_SECONDS`.

3. В доках и конфиге нужна была строгая политика скрытия служебных эндпоинтов
- Зафиксирован безопасный дефолт `KEYGEN_EXPOSE_DOCS=false` в приложении и infra.

4. Android release signing использовал fallback с тестовыми/заглушечными данными
- Убран dummy-вариант; релиз теперь использует реальные `key.properties` при наличии.

## Что проверено после исправлений

1. `flutter analyze` по изменённым Flutter security/login-файлам: ошибок нет.
2. `dart format` по изменённым Flutter-файлам.
3. `python -m py_compile app.py` для backend keygen.
4. Валидация `docker compose config`.
5. Пересборка и перезапуск keygen/nginx + smoke-check:
- `GET /keygen/healthz` -> `200`
- `GET /_matrix/client/versions` -> `200`
- `GET /_synapse/admin/v1/register` -> `404`
- `GET /keygen/docs` -> `404`
- `POST /keygen/token/create` без auth -> `401`

## Оставшиеся релизные риски

1. Нет полноценного автотеста E2E для цепочки QR invite + redeem + первый login bootstrap.
- Рекомендуется добавить хотя бы один CI smoke test на локальном docker-стеке.

2. Жизненный цикл access-token остаётся policy-driven (single-device поведение).
- Нужен чёткий support-flow в документации для восстановления аккаунта при потере устройства.

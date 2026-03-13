# Админский Runbook SecMess

Операционный гайд по генерации invite-QR, ролям, ротации master key и просмотру аудит-логов.

## 1) Что нужно для админских операций

1. Matrix `access_token` пользователя с ролью `admin`, `super-admin` или `developer`
2. Значение активного master key
3. HTTPS-доступ к keygen API (`https://<domain>/keygen/...`)

Защищённые методы требуют два заголовка:

- `Authorization: Bearer <MATRIX_ACCESS_TOKEN>`
- `X-Master-Key: <MASTER_KEY>`

Если `KEYGEN_MASTER_KEY_HEADER` изменён, используй это имя заголовка вместо `X-Master-Key`.

## 2) Проверить фактическую роль

```bash
curl -sS https://<domain>/keygen/auth/me \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>"
```

Пример ответа:

```json
{"user_id":"@admin:secmess.cloudpub.ru","role":"admin"}
```

## 3) Создать invite-токен и QR

```bash
curl -sS https://<domain>/keygen/token/create \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Ответ содержит:

1. `token`
2. `qr_payload`
3. `qr_png_base64`
4. `qr_svg`

Сохранить PNG из ответа:

```bash
curl -sS https://<domain>/keygen/token/create \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{}' | jq -r '.qr_png_base64' | base64 -d > invite.png
```

## 4) Управление ролями

Роли задаются в `infra/.env`:

1. `KEYGEN_ROLE_SUPER_ADMINS`
2. `KEYGEN_ROLE_ADMINS`
3. `KEYGEN_ROLE_DEVELOPERS`

Формат: Matrix ID через запятую.

Пример:

```env
KEYGEN_ROLE_SUPER_ADMINS=@owner:secmess.cloudpub.ru
KEYGEN_ROLE_ADMINS=@admin:secmess.cloudpub.ru,@ops:secmess.cloudpub.ru
KEYGEN_ROLE_DEVELOPERS=@aleks-dev:secmess.cloudpub.ru
```

Применить изменения ролей:

```bash
cd infra
docker compose --env-file .env -f docker-compose.yml up -d --build keygen
```

## 5) Ротация master key

Разрешённые роли: `super-admin`, `developer`

```bash
curl -sS https://<domain>/keygen/admin/master-key/rotate \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <CURRENT_MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"reason":"planned_rotation"}'
```

Важно:

1. `master_key` в ответе показывается один раз
2. Сохрани новый ключ офлайн сразу
3. Обнови `KEYGEN_MASTER_KEY` в `infra/.env`
4. Пересобери/перезапусти keygen

```bash
cd infra
docker compose --env-file .env -f docker-compose.yml up -d --build keygen
```

## 6) Просмотр админских аудит-событий

```bash
curl -sS "https://<domain>/keygen/admin/audit/events?limit=100" \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <MASTER_KEY>"
```

На что смотреть:

1. `actor_user_id`
2. `actor_role`
3. `action`
4. `status`
5. `master_key_id`
6. `created_at`

## 7) Если есть подозрение на компрометацию ключа

1. Немедленно ротируй master key
2. Обнови `KEYGEN_MASTER_KEY` в `infra/.env`
3. Перезапусти keygen с пересборкой
4. Выгрузи и проверь аудит-события
5. При необходимости временно сузь списки `admin`/`developer`

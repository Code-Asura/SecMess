# API Keygen (этап 5)

Базовый контракт сервиса одноразовых invite-токенов (QR) с RBAC и защитой админских методов через master key.

## Роли

- `super-admin`
- `admin`
- `developer`
- `user`

В текущей бизнес-модели роль `developer` считается ролью с максимальными правами.

## Аутентификация и заголовки

1. Заголовок Matrix-токена:
- `Authorization: Bearer <matrix_access_token>`

2. Заголовок master key (обязателен на защищённых админских методах):
- `X-Master-Key: <master_key_value>`
- Имя заголовка можно изменить через `KEYGEN_MASTER_KEY_HEADER`.

## 1) Получить роль текущего пользователя

`GET /keygen/auth/me`

Заголовки:

- `Authorization: Bearer <matrix_access_token>`

Ответ `200`:

```json
{
  "user_id": "@admin:secmess.cloudpub.ru",
  "role": "admin"
}
```

Ошибки:

- `401` - отсутствует/некорректный Matrix access token.
- `502` - ошибка интеграции с Synapse.

## 2) Создать invite-токен (защищённый метод)

`POST /keygen/token/create`

Заголовки:

- `Authorization: Bearer <matrix_access_token>`
- `X-Master-Key: <master_key_value>`
- `Content-Type: application/json`

Разрешённые роли:

- `admin`, `super-admin`, `developer`

Тело запроса:

```json
{
  "ttl_seconds": 900
}
```

`ttl_seconds` опционален. Если не передан, используется `KEYGEN_TOKEN_TTL_SECONDS`.
Верхняя граница задаётся через `KEYGEN_MAX_TTL_SECONDS`.

Ответ `200`:

```json
{
  "token_id": 1,
  "token": "....",
  "qr_payload": "secmess://invite?token=....",
  "expires_at": "2026-03-03T12:25:15.112497Z",
  "qr_png_base64": "...",
  "qr_svg": "<svg ...>"
}
```

Ошибки:

- `401` - отсутствует/некорректный Matrix токен или master key.
- `403` - роль не имеет права генерировать invite.
- `503` - master key не инициализирован.
- `502` - ошибка интеграции с Synapse.

## 3) Погасить токен (логин пользователя)

`POST /keygen/token/redeem`

Заголовки:

- `Content-Type: application/json`

Тело запроса:

```json
{
  "token": "....",
  "username": "optional_localpart",
  "display_name": "optional display"
}
```

Ответ `200`:

```json
{
  "user_id": "@user_xxxx:secmess.cloudpub.ru",
  "access_token": "syt_....",
  "home_server": "secmess.cloudpub.ru",
  "device_id": "...."
}
```

Ошибки:

- `404` - токен не найден.
- `410` - токен истёк или отозван.
- `409` - токен уже использован.
- `502` - ошибка интеграции с Synapse.

## 4) Информация об активном master key (защищённый метод)

`GET /keygen/admin/master-key`

Заголовки:

- `Authorization: Bearer <matrix_access_token>`
- `X-Master-Key: <master_key_value>`

Разрешённые роли:

- `admin`, `super-admin`, `developer`

Ответ `200`:

```json
{
  "key_id": "f2e741dca5bc2f07",
  "key_version": "smk1",
  "created_by": "@aleks-dev:secmess.cloudpub.ru",
  "created_at": "2026-03-10T18:22:51.122313Z"
}
```

## 5) Ротация master key (защищённый метод)

`POST /keygen/admin/master-key/rotate`

Заголовки:

- `Authorization: Bearer <matrix_access_token>`
- `X-Master-Key: <current_master_key>`
- `Content-Type: application/json`

Разрешённые роли:

- `super-admin`, `developer`

Тело (опционально):

```json
{
  "new_master_key": "smk1.customid123456.abcd....",
  "reason": "scheduled_rotation"
}
```

Примечания:

- Если `new_master_key` не передан, backend генерирует ключ автоматически.
- После ротации предыдущий активный ключ инвалидируется сразу.
- Новый ключ возвращается только один раз в этом ответе.

Ответ `200`:

```json
{
  "master_key": "smk1.4f6e0c1b0deab123.Df1....",
  "active_key_id": "4f6e0c1b0deab123",
  "previous_key_id": "f2e741dca5bc2f07",
  "rotated_at": "2026-03-10T18:30:09.003212Z"
}
```

Ошибки:

- `401` - невалидный текущий master key.
- `403` - роль не имеет права ротировать master key.
- `409` - конфликт ротации/повтор того же ключа.
- `422` - невалидный формат `new_master_key`.

## 6) Журнал админских событий (защищённый метод)

`GET /keygen/admin/audit/events?limit=50`

Заголовки:

- `Authorization: Bearer <matrix_access_token>`
- `X-Master-Key: <master_key_value>`

Разрешённые роли:

- `admin`, `super-admin`, `developer`

Ответ `200`:

```json
{
  "events": [
    {
      "id": 10,
      "actor_user_id": "@aleks-dev:secmess.cloudpub.ru",
      "actor_role": "developer",
      "action": "master_key.rotate",
      "status": "success",
      "master_key_id": "4f6e0c1b0deab123",
      "target": "f2e741dca5bc2f07->4f6e0c1b0deab123",
      "details": "scheduled_rotation",
      "created_at": "2026-03-10T18:30:09.009983Z"
    }
  ]
}
```

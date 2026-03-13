# План восстановления UI (форк FluffyChat)

Файл фиксирует текущую организацию UI-потока под MVP после переустановки чистого форка.

## Цель MVP (по TODO/TZ)

- Вход только по QR/одноразовому invite-token.
- Без обычной регистрации и без парольного логина.
- Без Spaces, публичного поиска и лишних веток мультиаккаунта.
- Жёстко заданный homeserver и keygen endpoint.

## Текущая конфигурация

- Центральный конфиг: `fluffychat/lib/config/secmess_config.dart`
- Ключевые параметры:
- `homeserverUrl`
- `keygenRedeemPath`
- флаги `enableSpaces`, `enablePublicSearch`, `enableMultiAccount`, `enableHomeserverSettings`

## Восстановленный login flow

1. Intro-экран ведёт в `QR Login`.
2. `QR Login` принимает токен из сканера или вручную.
3. Клиент вызывает `POST /keygen/token/redeem`.
4. Полученный `access_token` используется для инициализации Matrix client.
5. Далее стандартный переход в `/backup`.

Ключевой экран:

- `fluffychat/lib/pages/qr_login/qr_login_page.dart`

## Что отключено в UI для MVP

- Spaces-навигация и фильтрация.
- Публичный поиск rooms/users по серверу.
- Entry-point добавления второго аккаунта.
- Переход в настройки homeserver.
- Старые роуты `sign_in/sign_up/login` переадресуются в QR-flow.

## Ручная проверка (обязательно)

1. Скан QR с валидным токеном -> успешный вход.
2. Повторное использование токена -> ошибка `already used`.
3. Истекший токен -> ошибка `expired`.
4. После первого входа проверить создание ключей E2EE на устройстве.

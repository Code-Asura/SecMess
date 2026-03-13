# Сборка клиента SecMess (FluffyChat Android)

Инструкция по сборке APK и переключению целевого homeserver для debug/release.

## 1) Конфигурация homeserver

Базовые runtime-значения находятся в:

- `fluffychat/lib/config/secmess_config.dart`

Ключевые параметры:

1. `homeserverHost`
2. `homeserverUrl`
3. `keygenAuthMePath`
4. `keygenCreatePath`
5. `keygenRedeemPath`

Для релизов рекомендуется переопределять адреса через `--dart-define`, чтобы не хардкодить окружение в коде:

```powershell
flutter build apk --release `
  --dart-define=SECMESS_HOMESERVER_HOST=secmess.cloudpub.ru `
  --dart-define=SECMESS_HOMESERVER_URL=https://secmess.cloudpub.ru
```

## 2) Требования окружения (Windows)

1. Установлен Flutter SDK
2. Установлен Android SDK + platform tools
3. Работает `adb`

Проверка:

```powershell
flutter doctor
adb devices
```

## 3) Сборка debug APK

```powershell
cd fluffychat
flutter pub get
flutter clean
flutter build apk --debug
```

Результат:

- `fluffychat/build/app/outputs/flutter-apk/app-debug.apk`

## 4) Сборка release APK

Для production-подписи создай `fluffychat/android/key.properties`.
Если `key.properties` отсутствует, артефакт релиза будет собран без явной release-конфигурации подписи.

```powershell
cd fluffychat
flutter pub get
flutter clean
flutter build apk --release `
  --dart-define=SECMESS_HOMESERVER_HOST=secmess.cloudpub.ru `
  --dart-define=SECMESS_HOMESERVER_URL=https://secmess.cloudpub.ru
```

Результат:

- `fluffychat/build/app/outputs/flutter-apk/app-release.apk`

## 5) Установка APK на Android-устройство

Debug:

```powershell
adb install -r fluffychat/build/app/outputs/flutter-apk/app-debug.apk
```

Release:

```powershell
adb install -r fluffychat/build/app/outputs/flutter-apk/app-release.apk
```

## 6) Чеклист после сборки

1. Открывается экран QR/token-логина
2. Логин по токену проходит успешно
3. Для admin/developer доступна генерация QR в меню
4. Keygen-эндпоинты доступны через публичный туннель/домен
5. Работают текст, эмодзи, реакции и отправка статичных изображений
6. Звонки, voice/video, файлы и геолокация отключены в рамках MVP

## 7) Частые проблемы

1. `No devices found`
- Проверь `adb devices`, USB debugging, кабель и подтверждение доверенного хоста.

2. Белый экран после правок
- Выполни `flutter clean`, затем `flutter pub get` и пересборку.

3. Таймаут сети или `Token not found`
- Проверь туннель, публичный домен и доступность `/keygen/healthz`.

4. Ошибки из-за неверного домена
- Убедись, что `SECMESS_HOMESERVER_URL`, `MATRIX_PUBLIC_BASEURL` и фактический URL туннеля совпадают.

# Развёртывание SecMess на Ubuntu (Docker)

Этот гайд поднимает стек `synapse + postgres + keygen + nginx` с нуля и ориентирован на MVP-конфигурацию проекта.

## 1) Что нужно заранее

1. Ubuntu 22.04 или 24.04 (x86_64)
2. Публичная HTTPS-точка (домен, туннель или внешний reverse proxy)
3. Доступ к репозиторию SecMess

## 2) Установка зависимостей

```bash
sudo apt update
sudo apt -y install ca-certificates curl gnupg lsb-release git gettext-base openssl
```

Установка Docker Engine и Docker Compose plugin:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

## 3) Клонирование репозитория

```bash
git clone <YOUR_REPO_URL> SecMess
cd SecMess
```

## 4) Подготовка окружения (`infra/.env`)

Создай рабочий `.env` из шаблона:

```bash
cp infra/.env.example infra/.env
```

Проверь и заполни ключевые переменные:

1. Matrix/Synapse:
- `MATRIX_SERVER_NAME` (домен в MXID, например `secmess.cloudpub.ru`)
- `MATRIX_PUBLIC_BASEURL` (публичный URL, например `https://secmess.cloudpub.ru`)
- `SYNAPSE_REGISTRATION_SHARED_SECRET`
- `SYNAPSE_MACAROON_SECRET_KEY`
- `SYNAPSE_FORM_SECRET`

2. PostgreSQL:
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

3. Keygen:
- `KEYGEN_MASTER_KEY`
- `KEYGEN_TOKEN_HASH_SECRET`
- `KEYGEN_MASTER_KEY_HEADER`
- `KEYGEN_TOKEN_TTL_SECONDS`
- `KEYGEN_MAX_TTL_SECONDS`
- `KEYGEN_ROLE_SUPER_ADMINS`
- `KEYGEN_ROLE_ADMINS`
- `KEYGEN_ROLE_DEVELOPERS`

Генерация стойких секретов:

```bash
openssl rand -hex 32
openssl rand -base64 48 | tr '+/' '-_' | tr -d '='
```

## 5) Инициализация каталогов и `homeserver.yaml`

```bash
mkdir -p infra/volumes/postgres infra/volumes/synapse infra/volumes/certs
set -a
source infra/.env
set +a
envsubst < infra/synapse/homeserver.yaml.template > infra/volumes/synapse/homeserver.yaml
```

Если используешь `zsh/fish`, выполни эквивалентный экспорт переменных, чтобы `envsubst` видел значения из `.env`.

## 6) TLS-сертификат для nginx

Ожидаемые пути:

- `infra/volumes/certs/dev.crt`
- `infra/volumes/certs/dev.key`

Для локального теста/демо:

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout infra/volumes/certs/dev.key \
  -out infra/volumes/certs/dev.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Для production положи боевой сертификат и ключ в эти же пути.

## 7) Запуск стека

```bash
cd infra
docker compose --env-file .env -f docker-compose.yml up -d --build
docker compose --env-file .env -f docker-compose.yml ps
```

## 8) Базовые проверки после запуска

```bash
curl -sk https://localhost/healthz
curl -sk https://localhost/keygen/healthz
curl -sk https://localhost/_matrix/client/versions
curl -sk -o /dev/null -w "%{http_code}\n" https://localhost/_synapse/admin/v1/register
```

Ожидаемый результат:

1. Для первых трёх запросов статус `200`
2. Для `/_synapse/admin/...` статус `404` (доступ снаружи закрыт)

## 9) Публикация наружу (домен/туннель)

Пробрасывай наружу локальный порт `443`, так как именно на нём слушает `nginx` в текущем стеке.

После публикации обязательно проверь:

1. Публичный URL совпадает с `MATRIX_PUBLIC_BASEURL`
2. Клиент собирается с тем же хостом (`--dart-define=SECMESS_HOMESERVER_URL=...`)
3. Доступны эндпоинты:
- `https://<domain>/healthz`
- `https://<domain>/keygen/healthz`
- `https://<domain>/_matrix/client/versions`

## 10) Частые команды эксплуатации

```bash
cd infra
docker compose --env-file .env -f docker-compose.yml logs -f --tail 200
docker compose --env-file .env -f docker-compose.yml restart keygen
docker compose --env-file .env -f docker-compose.yml restart synapse nginx
docker compose --env-file .env -f docker-compose.yml down --remove-orphans
```

## 11) Частые проблемы

1. `503` в клиенте на `/keygen/...`
- Обычно не поднят туннель, либо неверный домен в клиентском конфиге.

2. `Token not found` сразу после генерации
- Токен уже истёк (`KEYGEN_TOKEN_TTL_SECONDS`) или запрос уходит в другой инстанс/домен.

3. Ошибки логина и инициализации E2EE
- Проверь, что Synapse доступен по `/_matrix/client/versions` с того же домена, что задан в приложении.

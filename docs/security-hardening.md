# Усиление безопасности VPS SecMess (MVP baseline)

Базовый hardening для Ubuntu VPS перед публичным запуском `synapse + keygen + nginx` в Docker.

## 1. Базовая подготовка ОС

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ufw fail2ban curl ca-certificates
sudo timedatectl set-timezone Europe/Moscow
```

Создай отдельного sudo-пользователя и отключи повседневную работу под `root`.

## 2. SSH hardening

Создай файл `/etc/ssh/sshd_config.d/99-secmess.conf`:

```text
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowTcpForwarding no
```

Применить:

```bash
sudo sshd -t
sudo systemctl restart ssh
```

Перед отключением `PasswordAuthentication` обязательно проверь вход по SSH-ключу из отдельной сессии.

## 3. UFW

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Если SSH работает на нестандартном порту, открой именно его и только потом включай UFW.

## 4. Fail2Ban

Создай `/etc/fail2ban/jail.d/secmess.local`:

```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-botsearch]
enabled = true
```

Применить:

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

## 5. Docker runtime baseline

- Запускай стек от отдельного пользователя (не от `root` в повседневной работе).
- Фиксируй версии образов на релизе, не оставляй `latest` на production.
- Для контейнеров включена ротация логов (`json-file`, `max-size`, `max-file`) в `infra/docker-compose.yml`.
- Не публикуй наружу порты `postgres`, `synapse`, `keygen`; внешний трафик только через `nginx`.

## 6. Еженедельный минимум проверок

- `sudo apt update && sudo apt -y upgrade`
- `sudo ufw status verbose`
- `sudo fail2ban-client status`
- `docker ps --format '{{.Names}} {{.Status}}'`
- Проверка ошибок приложения: `.\infra\scripts\dev.ps1 errors`

# Доступ к публичному серверу

Для автоматического развёртывания нужна только авторизация SSH-ключом для
`ubuntu@176.96.241.39`. Не передавайте пароль, приватный ключ или доступ к
GitHub. Откройте Web Console сервера у вашего хостинг-провайдера и выполните:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIH0y9v3D7RQ4PIac+zP1jGen11tz8j9B7fTumJHPm9Le ved-rtp-deploy' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
```

После этого агент использует локальный закрытый ключ автоматически:

```powershell
.\deploy-public.ps1
```

Скрипт сначала создаёт backup базы данных и файлов на сервере, затем
разворачивает только зафиксированный Git-коммит и проверяет `/api/health`.

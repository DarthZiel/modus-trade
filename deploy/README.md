# Развёртывание Iron Tech + Modus Feedback

Один VPS Basic-2 с 2 ГБ RAM, публичным IPv4, Linux amd64 и Docker Compose v2.
Основная ОС: Ubuntu 24.04 LTS. На старте используются 1456 МиБ
суммарных лимитов контейнеров (с ботом); фактическую нагрузку проверяем после
запуска. Это конфигурация небольшого пилота/защиты, не гарантия ёмкости.
В production используется только `compose.production.yaml`, без локального
`compose.yaml`. Имя проекта `irontech-production` отделяет данные от разработки.

## 1. Сборка на компьютере

Проверьте `docker info --format '{{.Architecture}}'`: архитектура компьютера
сборки и VPS должна совпадать. Для ARM нужен отдельный cross-build на amd64.

```bash
./deploy/build-release.sh v1
```

Образы собираются последовательно. В `releases/v1/` будут архив образов,
контрольная сумма, Compose и инструкции. `.env`, базы, демо-пользователи,
локальные ключи и вложения в пакет не включаются. `.dockerignore` исключает
виртуальные окружения, uploads и node_modules из контекста сборки.
При ошибке сборки каталог релиза остаётся для диагностики: повторите команду
с тем же тегом, Docker использует кеш. Готовый релиз с SHA256SUMS
перезаписать нельзя — для следующего релиза используйте новый тег.

## 2. Подготовка VPS

Нужны SSH-ключ, Docker Engine и Compose по официальной инструкции
https://docs.docker.com/engine/install/ubuntu/ . Проверка: `docker compose version`.
Настройте доступ SSH по ключу и firewall: разрешите действующий SSH-порт
**до** включения firewall, TCP 80/443 и при желании UDP 443. Не публикуйте
5432/8000/5173. При использовании UFW учтите, что Docker управляет своими
правилами; в Compose наружу публикуется только Caddy.

Для 2 ГБ RAM желательно добавить 2 ГБ swap (если его ещё нет), оставив
достаточно места на диске. Swap помогает пережить пики, но не заменяет RAM.
Не устанавливайте веб-панель и отдельный nginx, занимающие порты 80/443.
Диск должен вмещать загруженный архив, распакованные образы и данные приложения.
Перед импортом проверьте `df -h` и `docker system df`.

Замените `USER` и `VPS_IP` в командах реальными значениями:

```bash
ssh USER@VPS_IP 'sudo mkdir -p /opt/irontech && sudo chown "$(id -un):$(id -gn)" /opt/irontech'
scp -r releases/v1/. USER@VPS_IP:/opt/irontech/
ssh USER@VPS_IP
cd /opt/irontech
sha256sum -c SHA256SUMS
gzip -dc images.tar.gz | docker load
python3 deploy/init-env.py
```

Генератор создаёт `.env.production` с отдельными случайными DB/BOT-секретами
и режимом 600; существующий файл не перезаписывает. Не генерируйте новый пароль
для уже заполненного PostgreSQL volume: переменная не меняет пароль в БД.

Проверьте RELEASE_TAG в `.env.production` (должен совпасть с файлом RELEASE_TAG).
По умолчанию ИИ и бот отключены. Для ИИ задайте реальный провайдер/ключ/модель.
Не переносите локальный `.env` целиком и не публикуйте его в чате или логах.
Для бота нужны BOT_TOKEN, BOT_USERNAME и COMPOSE_PROFILES=bot.
Один Telegram-токен не должен одновременно использоваться polling-ботом
на компьютере и VPS; остановите локальный bot перед production-запуском.

## 3. DNS

Подтверждённый домен — **iron-tech.kz**, с дефисом. Проверка 9 ноября 2026:
NS = ns1.ps.kz / ns2.ps.kz / ns3.ps.kz; A = 82.115.48.196;
www CNAME = iron-tech.kz.; feedback A = 82.115.48.196. Ранние проверки
другого домена irontech.kz не относятся к этой DNS-зоне.
Перед изменениями повторите проверку:

```bash
dig +short NS iron-tech.kz
dig +short A iron-tech.kz
dig +short AAAA iron-tech.kz
dig +short A feedback.iron-tech.kz
dig +short AAAA feedback.iron-tech.kz
```

Редактируйте действующую авторитетную DNS-зону. Регистрация в PS.kz сама по
себе не означает, что DNS размещён там. Инструкция новой консоли PS.kz требует
ns1.ps.kz / ns2.ps.kz / ns3.ps.kz и созданной зоны:
https://docs.ps.kz/ru/domains/dns-management/manage-dns-records .
При необходимости переноса сначала скопируйте всю зону, включая MX, TXT,
SPF/DKIM/DMARC, CAA и записи проверки сервисов. Затем меняйте NS; при DNSSEC
согласуйте DS с новым DNS-оператором. Простая правка A в существующей зоне
предпочтительнее переноса NS, когда она доступна.

| Тип | Хост | Значение |
| --- | --- | --- |
| A | @ / iron-tech.kz | IPv4 VPS |
| A | feedback | IPv4 VPS |
| CNAME | www | iron-tech.kz. |

Существующую A основного домена меняйте только после загрузки образов и
готовности сервера: это переключит текущий сайт. Удалите устаревшие AAAA
**только для этих веб-имён**, если IPv6 на VPS не настроен; иначе часть
пользователей и проверка сертификата могут попадать на старый сервер.
Не добавляйте CNAME на имя, где остались A/AAAA. Сохраните прежние значения
для отката. TTL для переключения — 300 секунд, если DNS-панель позволяет;
старые кеши всё равно могут жить по прежнему TTL. PS.kz указывает 4–24 часа.
При наличии CAA убедитесь, что разрешён выбранный Caddy удостоверяющий центр.

## 4. Запуск и HTTPS

```bash
./deploy/compose.sh config --quiet
./deploy/compose.sh up -d --wait
./deploy/compose.sh ps
./deploy/compose.sh logs --tail 60 caddy
```

Caddy сам получает и продлевает сертификаты, перенаправляет HTTP на HTTPS.
Условия: домены направлены на VPS, доступны TCP 80/443, сохранён volume
caddy_data. https://caddyserver.com/docs/automatic-https . Не удаляйте его
между обновлениями. Не выводите `compose config` без `--quiet`: он содержит
раскрытые секреты. Команды не требуют публикации API или БД наружу.

API `/api/*` обрабатывается Caddy с удалением префикса, запросы уходят
на backend:8000; остальные — на frontend. Backend принимает proxy headers
из закрытой Docker-сети, cookie всегда Secure. Применяются миграции,
один Uvicorn worker, лимиты памяти, перезапуск после reboot и ротация логов.

Создайте реального первого координатора (не демо-аккаунты):

```bash
./deploy/compose.sh exec backend python -m app.bootstrap --email YOUR_EMAIL --name 'Ваше имя'
```

Пароль вводится интерактивно. В BotFather укажите Mini App URL
`https://feedback.iron-tech.kz` (корень, без /mini). В контейнерах он уже задан.

## 5. Проверка после переключения

```bash
curl -fsS https://iron-tech.kz/ -o /dev/null
curl -I http://iron-tech.kz/
curl -I https://www.iron-tech.kz/
curl -fsS https://feedback.iron-tech.kz/api/health
./deploy/compose.sh exec backend alembic current
docker stats --no-stream
```

Проверьте с телефона: лендинг и контакты, вход координатора, создание
приглашения, новое тестовое обращение, загрузка/скачивание файла, обсуждение,
результат и подтверждение. В Telegram — /start, Mini App и уведомление.
Cookie сессии должна иметь Secure/HttpOnly/SameSite=Lax, API — отвечать
`{"status":"ok","database":"connected"}`. Перезапустите контейнеры
и проверьте сохранность данных. Не используйте `down -v`.

## 6. Бэкапы и восстановление

```bash
./deploy/backup.sh
```

Скрипт блокирует параллельный запуск, запоминает работающие процессы записи,
останавливает backend/reminders/bot, делает pg_dump -Fc и архив uploads,
проверяет их чтение, запускает остановленные процессы даже при ошибке.
Во время копирования сервис кратко недоступен. Архив и checksum имеют
закрытые права, но **не зашифрованы**. Храните копии на другом устройстве
с ограниченным доступом. Незавершённые `.pending.*` не являются бэкапами.
Удаление старых архивов намеренно не автоматизировано; следите за диском.
`.env.production` сохраните отдельно в защищённом хранилище.

Пример ежедневного запуска через `crontab -e` на VPS (время по timezone VPS):

```cron
15 3 * * * cd /opt/irontech && ./deploy/backup.sh >> /opt/irontech/backups/cron.log 2>&1
```

Перед добавлением cron один раз выполните backup вручную; каталог backups
должен уже существовать. Регулярно копируйте архивы с сервера.

Для проверки восстановления используйте **отдельный** Compose-проект и новые
volumes, чтобы не затереть production. Распакуйте нужный архив в закрытый
каталог (`umask 077; tar -xf ...`), поднимите только db, затем:

```bash
# Отдельное имя проекта создаёт новые volumes. Caddy и bot не запускаем.
./deploy/compose.sh -p irontech-restore up -d --wait db
./deploy/compose.sh -p irontech-restore exec -T db sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database.dump
./deploy/compose.sh -p irontech-restore run --rm --no-deps -T --entrypoint tar backend xzf - -C /app/uploads < uploads.tar.gz
./deploy/compose.sh -p irontech-restore up -d --wait backend
./deploy/compose.sh -p irontech-restore exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

После восстановления проверьте /health; для проверки входа, истории обращения
и вложения подключите отдельный закрытый тестовый адрес, не production-домены.
Для фактического восстановления production сначала остановите все процессы
записи и сделайте отдельный бэкап текущего состояния. Восстановление поверх
непустой БД требует отдельного плана; команды выше предназначены для пустой БД.

## 7. Обновление

Сделайте backup, соберите новый тег на компьютере, перенесите/проверьте архив,
выполните docker load, поменяйте RELEASE_TAG, затем `./deploy/compose.sh up -d --wait`.
Сохраните старый архив и тег до проверки обновления. Откат образа не отменяет
миграции БД: совместимость миграций проверяется отдельно. Не запускайте
агрессивную очистку Docker volumes и не удаляйте предыдущие образы до проверки.

При отдельном обновлении лендинга задайте LANDING_RELEASE_TAG и выполните
`./deploy/compose.sh up -d --no-deps landing`. При следующем полном релизе
очистите LANDING_RELEASE_TAG, чтобы лендинг использовал общий RELEASE_TAG.

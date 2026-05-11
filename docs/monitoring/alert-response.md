# Alert Response Procedure

Документ описывает базовую процедуру реагирования на alerts в backend-проекте BudgetWiseBackend.

## Назначение

Процедура нужна, чтобы при срабатывании alerts быстро понять:

- что именно произошло;
- насколько проблема критична;
- где смотреть первичную информацию;
- какие проверки выполнить;
- какие действия предпринять;
- когда считать проблему решённой.

Alerts формируются Prometheus на основе метрик backend-сервиса и передаются в Alertmanager.

## Ответственные зоны

| Зона | Ответственный | Что проверяет |
|---|---|---|
| Backend API | Backend-разработчик | Ошибки API, 5xx, latency, доступность endpoints |
| База данных | Backend-разработчик | Доступность PostgreSQL, latency health-check |
| Мониторинг | Backend-разработчик | Prometheus, Alertmanager, Grafana |
| Инфраструктура dev-окружения | Backend-разработчик | Docker Compose, контейнеры, volume, network |

В рамках локального dev-окружения все роли выполняет разработчик проекта.

## Каналы уведомлений

В текущей dev-конфигурации используются локальные каналы:

| Канал | URL | Назначение |
|---|---|---|
| Prometheus Alerts | `http://127.0.0.1:9090/alerts` | Проверка состояния alerting rules |
| Alertmanager UI | `http://127.0.0.1:9093` | Просмотр активных и resolved alerts |
| Grafana Dashboard | `http://127.0.0.1:3000` | Анализ метрик и динамики проблемы |
| Docker logs | `docker compose logs ...` | Проверка логов сервисов |

В production-окружении дополнительно нужно подключить внешние уведомления:

- email;
- Telegram;
- Slack;
- webhook;
- incident management service.

## Уровни критичности

| Severity | Значение | Реакция |
|---|---|---|
| `critical` | Сервис недоступен, база недоступна, есть 5xx errors или degraded health | Реагировать сразу |
| `warning` | Повышенная latency или высокий уровень клиентских/API-ошибок | Проверить в ближайшее время |
| `info` | Информационное событие | Использовать для анализа, если такие alerts будут добавлены позже |

## Общий порядок реагирования

1. Открыть Alertmanager:

```text
http://127.0.0.1:9093
```

2. Определить alert:

```text
alertname
severity
service
description
startsAt
```

3. Открыть Prometheus alerts:

```text
http://127.0.0.1:9090/alerts
```

4. Открыть Grafana dashboard:

```text
http://127.0.0.1:3000
```

5. Проверить состояние контейнеров:

```bash
docker compose ps
```

6. Проверить health-check backend:

```bash
curl -i http://127.0.0.1:8000/health/
```

7. Проверить Prometheus metrics endpoint:

```bash
curl -i http://127.0.0.1:8000/metrics/
curl -i -H "X-Metrics-Token: budgetwise-metrics-dev-token" http://127.0.0.1:8000/metrics/
```

8. Проверить логи нужного сервиса:

```bash
docker compose logs backend --tail=100
docker compose logs prometheus --tail=100
docker compose logs alertmanager --tail=100
docker compose logs grafana --tail=100
```

9. Исправить причину.

10. Убедиться, что alert перешёл в resolved.

## Runbook: BackendDown

### Условие

```text
up{job="budgetwise-backend"} == 0
```

### Что означает

Prometheus не может собрать метрики с backend endpoint:

```text
http://backend:8000/metrics/
```

### Первичная проверка

```bash
docker compose ps backend
docker compose logs backend --tail=100
```

Проверить endpoint с хоста:

```bash
curl -i http://127.0.0.1:8000/health/
curl -i -H "X-Metrics-Token: budgetwise-metrics-dev-token" http://127.0.0.1:8000/metrics/
```

Проверить endpoint из контейнера Prometheus:

```bash
docker compose exec prometheus wget -qO- --header="X-Metrics-Token: budgetwise-metrics-dev-token" http://backend:8000/metrics/ | head
```

### Частые причины

- backend-контейнер не запущен;
- backend упал из-за ошибки импорта;
- порт `8000` недоступен;
- не установлена зависимость;
- неверный `METRICS_ACCESS_TOKEN`;
- `backend` отсутствует в `ALLOWED_HOSTS`;
- ошибка в `config/urls.py` или `apps/common/views.py`.

### Возможные действия

Перезапустить backend:

```bash
docker compose restart backend
```

Если менялись зависимости или Dockerfile:

```bash
docker compose up --build -d backend
```

Если менялись env-переменные:

```bash
docker compose up -d --force-recreate backend
```

### Критерий восстановления

Prometheus target должен стать `UP`:

```text
http://127.0.0.1:9090/targets
```

Alert `BackendDown` должен перейти в resolved.

## Runbook: BackendHealthDegraded

### Условие

```text
health_status == 0
```

### Что означает

Backend работает, но один из обязательных health-checks вернул ошибку.

### Первичная проверка

```bash
curl -i http://127.0.0.1:8000/health/
```

Проверить блок:

```json
{
  "checks": {
    "database": {},
    "redis": {},
    "celery": {},
    "external_services": {}
  }
}
```

### Частые причины

- недоступна база данных;
- ошибка подключения к обязательному сервису;
- health-check стал возвращать degraded;
- backend видит неправильные env-переменные.

### Возможные действия

Проверить контейнеры:

```bash
docker compose ps
```

Проверить backend-логи:

```bash
docker compose logs backend --tail=100
```

Проверить базу:

```bash
docker compose ps db
docker compose logs db --tail=100
```

### Критерий восстановления

`/health/` должен вернуть:

```json
{
  "status": "ok"
}
```

Метрика должна стать:

```text
health_status 1
```

## Runbook: DatabaseDown

### Условие

```text
database_up{alias="default"} == 0
```

### Что означает

Backend не может выполнить health-check PostgreSQL.

### Первичная проверка

```bash
docker compose ps db
docker compose logs db --tail=100
```

Проверить health-check backend:

```bash
curl http://127.0.0.1:8000/health/
```

Проверить настройки подключения:

```bash
docker compose exec backend python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default'])"
```

### Частые причины

- контейнер PostgreSQL не запущен;
- база ещё не прошла healthcheck;
- неверные `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`;
- backend запущен раньше базы;
- повреждён volume базы в dev-окружении.

### Возможные действия

Перезапустить базу:

```bash
docker compose restart db
```

Перезапустить backend после базы:

```bash
docker compose restart backend
```

Если проблема в dev-volume и данные не важны:

```bash
docker compose down
docker volume rm budgetwisebackend_postgres_data
docker compose up --build -d
```

### Критерий восстановления

В `/health/` должно быть:

```json
{
  "checks": {
    "database": {
      "status": "ok"
    }
  }
}
```

Метрика должна стать:

```text
database_up 1
```

## Runbook: High5xxErrorRate

### Условие

```text
sum(rate(api_server_errors_total[5m])) > 0
```

### Что означает

Backend начал возвращать серверные ошибки `5xx`.

### Первичная проверка

```bash
docker compose logs backend --tail=200
```

Проверить последние ошибки:

```bash
docker compose logs backend --tail=300 | grep -i "ERROR"
```

Проверить dashboard:

```text
Grafana -> BudgetWise Backend Overview -> 5xx Errors
```

### Частые причины

- необработанное исключение в view или serializer;
- ошибка в бизнес-логике;
- ошибка подключения к базе;
- некорректная миграция;
- ошибка импорта после изменения кода;
- неправильная env-конфигурация.

### Возможные действия

1. Найти traceback в логах.
2. Определить endpoint, который возвращает `500`.
3. Воспроизвести запрос через curl или Postman.
4. Исправить код.
5. Запустить тесты:

```bash
python manage.py check
python manage.py test apps.common apps.finance apps.users
```

6. Перезапустить backend:

```bash
docker compose restart backend
```

### Критерий восстановления

- новые `5xx` не появляются;
- alert перешёл в resolved;
- автотесты проходят;
- endpoint возвращает ожидаемый HTTP-код.

## Runbook: HighApiErrorRate

### Условие

```text
sum(rate(api_errors_total[5m])) > 0.1
```

### Что означает

Количество API-ошибок стало слишком высоким.

API-ошибки могут включать:

- `400 Bad Request`;
- `401 Unauthorized`;
- `403 Forbidden`;
- `404 Not Found`;
- `409 Conflict`;
- `422 Unprocessable Entity`, если будет добавлен позже.

### Первичная проверка

Открыть Grafana:

```text
API errors by code
RPS by status code
```

Проверить метрики в Prometheus:

```text
api_errors_total
api_auth_errors_total
api_validation_errors_total
```

Проверить backend-логи:

```bash
docker compose logs backend --tail=200
```

### Частые причины

- frontend отправляет некорректные данные;
- истёк JWT token;
- пользователь не авторизован;
- изменился API contract;
- массовые ошибки валидации;
- неверные query-параметры;
- попытка удалить объект со связанными сущностями.

### Возможные действия

1. Определить `code` и `status_code` в Grafana.
2. Найти endpoint по label `path`.
3. Проверить актуальность API contract.
4. Проверить serializer validation.
5. Проверить frontend-запрос или Postman-коллекцию.
6. Если ошибка ожидаемая, убедиться, что frontend корректно её обрабатывает.

### Критерий восстановления

- error rate вернулся к нормальному уровню;
- frontend корректно показывает ошибку пользователю;
- если это баг, добавлен негативный автотест.

## Runbook: HighP95Latency

### Условие

```text
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 1
```

### Что означает

95 процентов запросов обрабатываются дольше 1 секунды.

### Первичная проверка

Открыть Grafana:

```text
p95 latency by path
```

Проверить, какой endpoint медленный.

Проверить backend-логи:

```bash
docker compose logs backend --tail=200
```

### Частые причины

- медленный SQL-запрос;
- отсутствует индекс;
- слишком большой ответ;
- неоптимальный queryset;
- N+1 queries;
- блокировка базы;
- тяжёлая синхронная операция в request-response цикле.

### Возможные действия

1. Определить медленный endpoint.
2. Проверить queryset.
3. Добавить `select_related` или `prefetch_related`, если нужно.
4. Проверить индексы.
5. Проверить пагинацию.
6. Вынести тяжёлые задачи в background processing, если это применимо.
7. Добавить тест или заметку в backlog.

### Критерий восстановления

- p95 latency ниже threshold;
- endpoint стабильно отвечает в ожидаемое время;
- нет роста ошибок и timeout.

## Runbook: HighDatabaseCheckLatency

### Условие

```text
histogram_quantile(0.95, sum(rate(database_check_duration_seconds_bucket[5m])) by (le)) > 0.5
```

### Что означает

Проверка доступности PostgreSQL стала выполняться медленно.

### Первичная проверка

```bash
curl http://127.0.0.1:8000/health/
docker compose logs db --tail=100
```

Проверить dashboard:

```text
Database check duration p95
Database Up
```

### Частые причины

- база перегружена;
- контейнеру не хватает ресурсов;
- медленный диск;
- проблема с Docker/WSL;
- база выполняет тяжёлые запросы;
- слишком много подключений.

### Возможные действия

1. Проверить состояние контейнера БД.
2. Проверить логи PostgreSQL.
3. Проверить ресурсы Docker Desktop/WSL.
4. Перезапустить dev-окружение, если проблема инфраструктурная.
5. Если проблема повторяется, вынести в отдельную задачу анализа производительности.

### Критерий восстановления

- `database_up` равно `1`;
- latency проверки БД ниже threshold;
- `/health/` возвращает `status: ok`.

## Закрытие инцидента

Проблему можно считать закрытой, если:

- alert перешёл в resolved;
- сервисы находятся в состоянии `Up`;
- `/health/` возвращает `200 OK`;
- Prometheus target находится в состоянии `UP`;
- Grafana показывает нормальные значения;
- причина проблемы понятна и зафиксирована;
- если это баг, создана задача или добавлен тест.

## Что фиксировать после проблемы

После серьёзного alert нужно зафиксировать:

| Поле | Описание |
|---|---|
| Дата и время | Когда alert сработал |
| Alert name | Название alert |
| Severity | Critical или warning |
| Причина | Что вызвало проблему |
| Что сделали | Какие действия помогли |
| Время восстановления | Когда alert resolved |
| Follow-up | Нужны ли правки кода, тестов, документации или инфраструктуры |

## Шаблон короткого отчёта

```text
Alert:
Severity:
Start time:
End time:
Affected service:
Root cause:
Actions taken:
Result:
Follow-up:
```

## Связанные документы

| Документ | Назначение |
|---|---|
| `docs/monitoring/metrics.md` | Перечень ключевых метрик |
| `docs/monitoring/prometheus.md` | Prometheus-compatible metrics endpoint |
| `docs/monitoring/grafana.md` | Grafana dashboard |
| `docs/monitoring/alerts.md` | Alerting rules |
| `docs/monitoring/health-checks.md` | Health-check endpoints |
# Grafana Dashboards

Документ описывает настройку dashboards для мониторинга backend API проекта BudgetWiseBackend.

## Назначение

Grafana используется для визуализации метрик, которые собираются Prometheus с endpoint:

```text
GET /metrics/
```

Основной dashboard:

```text
BudgetWise Backend Overview
```

Dashboard нужен, чтобы быстро видеть состояние backend-сервиса, базы данных, количество запросов, ошибки и время ответа API.

## Сервисы

В `docker-compose.yml` добавлены сервисы:

| Сервис | URL | Назначение |
|---|---|---|
| `prometheus` | `http://127.0.0.1:9090` | Сбор и хранение метрик |
| `grafana` | `http://127.0.0.1:3000` | Визуализация метрик |

Backend отдаёт метрики по адресу:

```text
http://backend:8000/metrics/
```

Prometheus обращается к backend внутри docker-сети по имени сервиса:

```text
backend:8000
```

## Доступ к Grafana

Данные для входа задаются через `.env`:

```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

Для локальной разработки используются значения по умолчанию:

```text
login: admin
password: admin
```

В production-окружении пароль администратора нужно заменить на безопасный.

## Доступ к Prometheus metrics

Endpoint `/metrics/` защищён заголовком:

```http
X-Metrics-Token: <metrics_access_token>
```

Значение token задаётся через переменную окружения:

```env
METRICS_ACCESS_TOKEN=budgetwise-metrics-dev-token
```

Prometheus использует этот token при сборе метрик.

## Provisioning

Grafana автоматически подхватывает datasource и dashboard из файлов:

```text
monitoring/grafana/provisioning/datasources/prometheus.yml
monitoring/grafana/provisioning/dashboards/dashboards.yml
monitoring/grafana/dashboards/budgetwise-backend-overview.json
```

Datasource:

```text
Prometheus
```

Datasource UID:

```text
prometheus
```

Dashboard автоматически создаётся в папке:

```text
BudgetWise
```

## Dashboard

Основной dashboard:

```text
BudgetWise Backend Overview
```

Файл dashboard:

```text
monitoring/grafana/dashboards/budgetwise-backend-overview.json
```

## Dashboard panels

Dashboard `BudgetWise Backend Overview` содержит панели:

| Панель | Метрика | Назначение |
|---|---|---|
| Backend Health | `health_status` | Общий статус backend |
| Database Up | `database_up` | Доступность базы данных |
| Total Requests | `http_requests_total` | Общее количество HTTP-запросов |
| 5xx Errors | `api_server_errors_total` | Количество серверных ошибок |
| RPS by status code | `rate(http_requests_total[1m])` | Количество запросов в секунду по HTTP-кодам |
| p95 latency by path | `http_request_duration_seconds_bucket` | p95 latency по endpoints |
| API errors by code | `api_errors_total` | Ошибки API по status code и error code |
| Database check duration p95 | `database_check_duration_seconds_bucket` | Время проверки PostgreSQL |

## Используемые метрики

Dashboard использует метрики, которые отдаёт backend:

| Метрика | Тип | Назначение |
|---|---|---|
| `http_requests_total` | counter | Общее количество HTTP-запросов |
| `http_request_duration_seconds` | histogram | Время обработки HTTP-запросов |
| `http_requests_in_progress` | gauge | Количество запросов в обработке |
| `api_errors_total` | counter | Количество API-ошибок |
| `api_server_errors_total` | counter | Количество серверных ошибок |
| `api_validation_errors_total` | counter | Количество ошибок валидации |
| `api_auth_errors_total` | counter | Количество ошибок авторизации |
| `api_request_size_bytes` | histogram | Размер HTTP-запросов |
| `api_response_size_bytes` | histogram | Размер HTTP-ответов |
| `database_up` | gauge | Доступность базы данных |
| `database_check_duration_seconds` | histogram | Время проверки базы данных |
| `health_status` | gauge | Общий статус backend health-check |

## Запуск

Запустить окружение:

```bash
docker compose up --build -d
```

Проверить состояние контейнеров:

```bash
docker compose ps
```

Ожидаемые сервисы:

```text
budgetwise-backend
budgetwise-db
budgetwise-prometheus
budgetwise-grafana
```

## Проверка backend

Проверить health-check:

```bash
curl http://127.0.0.1:8000/health/
```

Ожидаемый результат:

```json
{
  "status": "ok",
  "service": "BudgetWiseBackend",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "ok"
    }
  }
}
```

Проверить metrics endpoint без token:

```bash
curl -i http://127.0.0.1:8000/metrics/
```

Ожидаемый результат:

```text
HTTP 403
```

Проверить metrics endpoint с token:

```bash
curl -H "X-Metrics-Token: budgetwise-metrics-dev-token" http://127.0.0.1:8000/metrics/
```

Ожидаемый результат:

```text
# HELP http_requests_total Total number of HTTP requests.
# TYPE http_requests_total counter
```

## Проверка Prometheus

Проверить готовность Prometheus:

```bash
curl http://127.0.0.1:9090/-/ready
```

Ожидаемый результат:

```text
Prometheus Server is Ready.
```

Открыть Prometheus в браузере:

```text
http://127.0.0.1:9090
```

Проверить targets:

```text
http://127.0.0.1:9090/targets
```

Target должен быть:

```text
budgetwise-backend
```

Статус target должен быть:

```text
UP
```

Если target находится в статусе `DOWN`, нужно проверить:

1. Работает ли backend-контейнер.
2. Доступен ли endpoint `/metrics/`.
3. Совпадает ли `METRICS_ACCESS_TOKEN` в `.env` и `monitoring/prometheus/prometheus.yml`.
4. Нет ли ошибок в логах backend или Prometheus.

Проверить логи Prometheus:

```bash
docker compose logs prometheus --tail=100
```

## Проверка Grafana

Проверить health endpoint Grafana:

```bash
curl http://127.0.0.1:3000/api/health
```

Ожидаемый результат:

```json
{
  "database": "ok",
  "version": "...",
  "commit": "..."
}
```

Открыть Grafana в браузере:

```text
http://127.0.0.1:3000
```

Войти с локальными данными:

```text
login: admin
password: admin
```

Открыть dashboard:

```text
Dashboards -> BudgetWise -> BudgetWise Backend Overview
```

Если dashboard не появился сразу, нужно подождать 30 секунд или перезапустить Grafana:

```bash
docker compose restart grafana
```

Проверить логи Grafana:

```bash
docker compose logs grafana --tail=100
```

## Что смотреть в первую очередь

При проверке dashboard нужно обратить внимание на следующие панели:

1. `Backend Health` должен показывать `ok`.
2. `Database Up` должен показывать `up`.
3. `Total Requests` должен увеличиваться после обращений к API.
4. `RPS by status code` должен показывать запросы по HTTP-кодам.
5. `p95 latency by path` должен показывать время ответа endpoints.
6. `API errors by code` должен расти при ошибках `400`, `401`, `403`, `409`.
7. `5xx Errors` в норме должен быть `0`.
8. `Database check duration p95` должен оставаться небольшим и стабильным.

## Как сгенерировать тестовый трафик

Можно выполнить несколько запросов к backend:

```bash
curl http://127.0.0.1:8000/health/
curl http://127.0.0.1:8000/api/v1/
curl http://127.0.0.1:8000/api/v1/finance/categories/
curl -H "X-Metrics-Token: budgetwise-metrics-dev-token" http://127.0.0.1:8000/metrics/
```

Запрос к защищённому endpoint без JWT специально создаст ошибку `401`, которая должна попасть в метрики ошибок.

## Возможные проблемы

### Prometheus target DOWN

Проверить:

```bash
docker compose ps
docker compose logs backend --tail=100
docker compose logs prometheus --tail=100
```

Частые причины:

- backend не запущен;
- в контейнере backend не установлена зависимость `prometheus-client`;
- endpoint `/metrics/` возвращает `403`;
- в `prometheus.yml` указан неправильный token;
- backend недоступен по имени `backend:8000` внутри docker-сети.

### Grafana не показывает dashboard

Проверить:

```bash
docker compose logs grafana --tail=100
```

Частые причины:

- ошибка в JSON dashboard;
- неверный путь provisioning;
- не примонтирована папка `monitoring/grafana/dashboards`;
- datasource UID в dashboard не совпадает с UID datasource.

Datasource UID должен быть:

```text
prometheus
```

### Панели пустые

Возможные причины:

- Prometheus ещё не собрал метрики;
- target `budgetwise-backend` в статусе `DOWN`;
- backend ещё не получил запросы;
- временной диапазон dashboard слишком маленький;
- метрика ещё не была создана, потому что соответствующее событие не происходило.

Для проверки можно открыть в Prometheus expression browser и выполнить:

```text
http_requests_total
```

или:

```text
health_status
```

## Безопасность

Dashboard и метрики не должны содержать:

- JWT token;
- password;
- email пользователя;
- username пользователя;
- суммы операций;
- описания операций;
- названия пользовательских счетов;
- названия пользовательских категорий.

В dashboard используются только технические labels:

- method;
- path;
- status_code;
- code;
- alias;
- vendor.

## Production notes

Текущая настройка предназначена для локального dev-окружения.

Для production нужно отдельно настроить:

- безопасный пароль администратора Grafana;
- закрытый доступ к Grafana;
- защищённый доступ к Prometheus;
- хранение секретов не в `.env`, а в secret manager или аналогичном механизме;
- отдельное хранилище данных Prometheus и Grafana;
- резервное копирование dashboards;
- alerts и notification channels.

## Связанные документы

| Документ | Назначение |
|---|---|
| `docs/monitoring/metrics.md` | Перечень ключевых метрик |
| `docs/monitoring/health-checks.md` | Health-check endpoints |
| `docs/monitoring/prometheus.md` | Prometheus-compatible metrics endpoint |
| `docs/api-errors.md` | Контракт ошибок API |
| `docs/api-contract.md` | Общий контракт API |
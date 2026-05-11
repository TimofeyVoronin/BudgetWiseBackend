# Prometheus Metrics

Документ описывает подключение Prometheus-compatible метрик в backend API проекта BudgetWiseBackend.

## Endpoint

```text
GET /metrics/
```

Endpoint возвращает метрики в Prometheus text format.

## Доступ

Endpoint защищён заголовком:

```http
X-Metrics-Token: <metrics_access_token>
```

Значение token задаётся через переменную окружения:

```env
METRICS_ACCESS_TOKEN=budgetwise-metrics-dev-token
```

Если token не передан или передан неверно, backend возвращает `403`.

## Проверка вручную

```bash
curl -H "X-Metrics-Token: $METRICS_ACCESS_TOKEN" http://127.0.0.1:8000/metrics/
```

Ожидаемый результат:

```text
# HELP http_requests_total Total number of HTTP requests.
# TYPE http_requests_total counter
```

## Собираемые метрики

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

## Labels

HTTP-метрики используют labels:

| Label | Описание |
|---|---|
| `method` | HTTP-метод |
| `path` | Endpoint или route |
| `status_code` | HTTP-код ответа |

Error-метрики используют labels:

| Label | Описание |
|---|---|
| `status_code` | HTTP-код ошибки |
| `code` | Код ошибки из API error contract |
| `path` | Endpoint |
| `field` | Поле с ошибкой валидации, если применимо |

Database-метрики используют labels:

| Label | Описание |
|---|---|
| `alias` | Alias базы данных Django |
| `vendor` | Backend базы данных, например `postgresql` |

## Пример Prometheus scrape config

```yaml
scrape_configs:
  - job_name: "budgetwise-backend"
    metrics_path: "/metrics/"
    static_configs:
      - targets:
          - "backend:8000"
    authorization:
      credentials: "budgetwise-metrics-dev-token"
```

Если используется заголовок `X-Metrics-Token`, в production-конфигурации Prometheus нужно настроить передачу этого заголовка через reverse proxy или дополнительную scrape-конфигурацию.

## Безопасность

В метрики нельзя добавлять:

- access token;
- refresh token;
- password;
- email пользователя;
- username пользователя;
- описание финансовой операции;
- сумму операции конкретного пользователя;
- название пользовательской категории;
- название пользовательского счёта.

Допустимые labels:

- HTTP method;
- endpoint path;
- status code;
- error code;
- field name;
- database alias;
- database vendor.

## Связанные документы

| Документ | Назначение |
|---|---|
| `docs/monitoring/metrics.md` | Перечень ключевых метрик |
| `docs/monitoring/health-checks.md` | Health-check endpoints |
| `docs/api-errors.md` | Контракт ошибок API |
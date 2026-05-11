# Health Checks

Документ описывает health-check endpoints backend API проекта BudgetWiseBackend.

## Endpoint

```text
GET /health/
```

Endpoint публичный и не требует JWT.

Назначение:

- проверить, что backend отвечает;
- проверить доступность PostgreSQL;
- показать состояние будущих зависимостей: Redis, Celery, external services;
- использовать endpoint в Docker, мониторинге и ручной диагностике.

## Формат ответа

```json
{
  "status": "ok",
  "service": "BudgetWiseBackend",
  "version": "1.0.0",
  "timestamp": "2026-05-10T00:00:00Z",
  "checks": {
    "database": {
      "status": "ok",
      "required": true,
      "latency_ms": 2.15,
      "details": {
        "alias": "default",
        "vendor": "postgresql"
      }
    },
    "redis": {
      "status": "skipped",
      "required": false,
      "latency_ms": null,
      "details": {
        "reason": "Redis is not configured yet."
      }
    },
    "celery": {
      "status": "skipped",
      "required": false,
      "latency_ms": null,
      "details": {
        "reason": "Celery health-check is not configured yet."
      }
    },
    "external_services": {
      "status": "skipped",
      "required": false,
      "latency_ms": null,
      "details": {
        "reason": "External services are not configured yet."
      }
    }
  }
}
```

## Статусы проверки

| Статус | Описание |
|---|---|
| `ok` | Проверка успешно пройдена |
| `error` | Проверка завершилась ошибкой |
| `skipped` | Проверка не выполняется, потому что зависимость пока не настроена |

## Общий статус

| `status` | HTTP-код | Описание |
|---|---|---|
| `ok` | `200` | Все обязательные проверки успешны |
| `degraded` | `503` | Минимум одна обязательная проверка завершилась ошибкой |

На текущем этапе обязательная проверка:

```text
database
```

Необязательные проверки:

```text
redis
celery
external_services
```

Они помечены как `skipped`, потому что соответствующие зависимости пока не подключены в текущем scope.

## Проверка PostgreSQL

Backend проверяет соединение с PostgreSQL через простой SQL-запрос:

```sql
SELECT 1
```

В ответе отображаются:

| Поле | Описание |
|---|---|
| `status` | Результат проверки |
| `required` | Является ли зависимость обязательной |
| `latency_ms` | Время проверки в миллисекундах |
| `details.alias` | Alias базы данных Django |
| `details.vendor` | Используемый backend базы данных |

## Проверка вручную

```bash
curl http://127.0.0.1:8000/health/
```

Ожидаемый результат при работающей базе данных:

```text
HTTP 200
```

и поле:

```json
{
  "status": "ok"
}
```

## Использование в Docker Compose

Endpoint можно использовать для проверки состояния backend-контейнера.

Пример команды:

```bash
curl -f http://127.0.0.1:8000/health/
```

Если PostgreSQL недоступен, endpoint должен вернуть `503`, и health-check должен считаться неуспешным.

## План расширения

В будущих задачах можно добавить реальные проверки:

- Redis;
- Celery worker;
- Celery Beat;
- внешнего API чеков;
- email-провайдера;
- object storage для media/static файлов, если появится.
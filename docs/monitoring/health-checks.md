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
- проверить Redis, если включён `REDIS_HEALTH_ENABLED`;
- проверить Celery worker, если включён `CELERY_HEALTH_ENABLED`;
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
      "status": "ok",
      "required": false,
      "latency_ms": 1.31,
      "details": {
        "url": "redis://redis:6379/0"
      }
    },
    "celery": {
      "status": "ok",
      "required": false,
      "latency_ms": 8.42,
      "details": {
        "brokerUrl": "redis://redis:6379/0",
        "workersOnline": 1,
        "workers": ["celery@worker"]
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

Если Redis или Celery health-check выключен, соответствующая проверка вернёт `skipped`.

## Статусы проверки

| Статус | Описание |
|---|---|
| `ok` | Проверка успешно пройдена |
| `error` | Проверка завершилась ошибкой |
| `skipped` | Проверка не выполняется, потому что зависимость отключена или не настроена |

## Общий статус

| `status` | HTTP-код | Описание |
|---|---|---|
| `ok` | `200` | Все обязательные проверки успешны |
| `degraded` | `503` | Минимум одна обязательная проверка завершилась ошибкой |

Обязательная проверка по умолчанию:

```text
database
```

Redis и Celery по умолчанию необязательные. Это сделано, чтобы backend мог продолжать отвечать даже при временной недоступности фоновой очереди. Если нужно сделать их обязательными, включаются переменные:

```env
REDIS_HEALTH_REQUIRED=True
CELERY_HEALTH_REQUIRED=True
```

## Проверка PostgreSQL

Backend проверяет соединение с PostgreSQL через простой SQL-запрос:

```sql
SELECT 1
```

## Проверка Redis

Redis проверяется командой `PING` через URL из переменных:

```env
REDIS_HEALTH_URL=redis://redis:6379/0
REDIS_URL=redis://redis:6379/0
```

Проверка включается так:

```env
REDIS_HEALTH_ENABLED=True
```

## Проверка Celery

Celery проверяется через ping worker-процессов. Для локального Docker Compose worker запускается сервисом:

```text
celery_worker
```

Проверка включается так:

```env
CELERY_HEALTH_ENABLED=True
```

## Проверка вручную

```bash
curl http://127.0.0.1:8000/health/
```

Ожидаемый результат при работающих обязательных зависимостях:

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

Если PostgreSQL недоступен, endpoint вернёт `503`. Если Redis или Celery недоступны, общий статус станет `degraded` только при включённых `REDIS_HEALTH_REQUIRED=True` или `CELERY_HEALTH_REQUIRED=True`.

# Monitoring Alerts

Документ описывает alerting rules для мониторинга backend API проекта BudgetWiseBackend.

## Назначение

Alerts используются для автоматического обнаружения проблем в backend-сервисе, базе данных и API.

Prometheus оценивает alerting rules по расписанию. Если условие остаётся истинным в течение указанного времени, alert переходит в состояние firing.

Alertmanager принимает alerts от Prometheus, группирует их и отображает в web-интерфейсе.

## Сервисы

| Сервис | URL | Назначение |
|---|---|---|
| Prometheus | `http://127.0.0.1:9090` | Оценка alerting rules |
| Alertmanager | `http://127.0.0.1:9093` | Группировка и отображение alerts |
| Grafana | `http://127.0.0.1:3000` | Визуализация метрик |

## Файлы

| Файл | Назначение |
|---|---|
| `monitoring/prometheus/prometheus.yml` | Основная конфигурация Prometheus |
| `monitoring/prometheus/alerts/backend-alerts.yml` | Alerting rules для backend |
| `monitoring/alertmanager/alertmanager.yml` | Конфигурация Alertmanager |

## Alerting rules

| Alert | Severity | Условие | Назначение |
|---|---|---|---|
| `BackendDown` | critical | `up{job="budgetwise-backend"} == 0` | Backend metrics endpoint недоступен |
| `BackendHealthDegraded` | critical | `health_status == 0` | Health-check backend находится в degraded-состоянии |
| `DatabaseDown` | critical | `database_up{alias="default"} == 0` | База данных недоступна |
| `High5xxErrorRate` | critical | `sum(rate(api_server_errors_total[5m])) > 0` | Backend возвращает 5xx errors |
| `HighApiErrorRate` | warning | `sum(rate(api_errors_total[5m])) > 0.1` | Повышенное количество API-ошибок |
| `HighP95Latency` | warning | `p95 latency > 1s` | Замедление API |
| `HighDatabaseCheckLatency` | warning | `database p95 latency > 0.5s` | Замедление проверки PostgreSQL |

## Проверка конфигурации

Проверить Prometheus config:

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

Проверить alerting rules:

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/alerts/backend-alerts.yml
```

Проверить Alertmanager config:

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

## Проверка Prometheus alerts

Открыть:

```text
http://127.0.0.1:9090/alerts
```

Alerts должны отображаться в списке правил.

В нормальном состоянии критические alerts должны быть inactive.

## Проверка Alertmanager

Открыть:

```text
http://127.0.0.1:9093
```

Если alerts firing, они появятся в Alertmanager UI.

## Проверка через API

Prometheus rules API:

```bash
curl http://127.0.0.1:9090/api/v1/rules
```

Prometheus alerts API:

```bash
curl http://127.0.0.1:9090/api/v1/alerts
```

Alertmanager status API:

```bash
curl http://127.0.0.1:9093/api/v2/status
```

## Как искусственно проверить BackendDown

Остановить backend:

```bash
docker compose stop backend
```

Подождать 1-2 минуты.

Проверить:

```text
http://127.0.0.1:9090/alerts
http://127.0.0.1:9093
```

Alert `BackendDown` должен перейти в состояние firing.

Вернуть backend:

```bash
docker compose start backend
```

Через некоторое время alert должен перейти в resolved.

## Как проверить ошибочные запросы

Можно создать несколько запросов без JWT:

```bash
curl http://127.0.0.1:8000/api/v1/finance/categories/
curl http://127.0.0.1:8000/api/v1/users/me/
```

Эти запросы создадут `401` и увеличат метрики:

```text
api_errors_total
api_auth_errors_total
```

## Production notes

Текущая конфигурация предназначена для локального dev-окружения.

Для production нужно добавить реальные notification channels:

- email;
- Telegram;
- Slack;
- webhook;
- incident management service.

Также нужно настроить:

- отдельные thresholds для production;
- silence rules;
- routing по severity;
- ответственных за обработку alerts;
- runbook для каждого critical alert.

## Связанные документы

| Документ | Назначение |
|---|---|
| `docs/monitoring/metrics.md` | Перечень ключевых метрик |
| `docs/monitoring/prometheus.md` | Prometheus-compatible metrics endpoint |
| `docs/monitoring/grafana.md` | Grafana dashboard |
| `docs/monitoring/health-checks.md` | Health-check endpoints |
| `docs/monitoring/alert-response.md` | Процедура реагирования на alerts |
# User financial recommendations API contract

## Назначение

Модуль рекомендаций формирует персонализированные финансовые рекомендации на основе уже существующих данных пользователя: операций, бюджетов, целей, планируемых платежей, onboarding-ответов и результатов Financial Health Check.

В первой версии используется rule-based подход. ML-модель в этой задаче не подключается, потому что интеграция с ML вынесена в отдельную задачу BUD-233.

## Архитектурное решение

```text
Модуль: apps/finance/recommendations/
Тип генерации: rule-based
Хранение в БД: FinancialRecommendation и FinancialRecommendationEvent
Источники данных: Financial Health Check, budgets, goals, transactions, planned transactions, onboarding
ML: не используется
```

Рекомендации Financial Health Check остаются расчётными подсказками внутри health-check summary. В этом модуле рекомендации становятся полноценными карточками: их можно хранить, показывать списком, принимать, скрывать, откладывать и анализировать по событиям.


## Модели хранения

### `FinancialRecommendation`

Модель хранит карточку рекомендации, которую можно показать пользователю, принять, скрыть или отложить.

Ключевые поля:

```text
user
code
type
priority
status
title
text
action
reason
source
source_key
context
expires_at
snoozed_until
accepted_at
hidden_at
created_at
updated_at
```

`source_key` используется для защиты от дублей при повторной генерации. Например, одна и та же активная рекомендация `create_budget` от источника `financial_health` не должна создаваться несколько раз подряд.

### `FinancialRecommendationEvent`

Модель хранит историю действий пользователя с рекомендацией.

Ключевые поля:

```text
recommendation
user
event_type
metadata
created_at
updated_at
```

События нужны для будущей статистики, оценки эффективности рекомендаций и корректной обработки действий пользователя.

## Будущие endpoints

```http
GET  /api/v1/finance/recommendations/meta/
GET  /api/v1/finance/recommendations/
POST /api/v1/finance/recommendations/refresh/
POST /api/v1/finance/recommendations/{id}/accept/
POST /api/v1/finance/recommendations/{id}/hide/
POST /api/v1/finance/recommendations/{id}/snooze/
GET  /api/v1/finance/recommendations/stats/
```

## Типы рекомендаций

| Type | Назначение |
| --- | --- |
| `budget` | Бюджеты и лимиты расходов |
| `saving` | Сбережения и доля накоплений |
| `goal` | Финансовые цели |
| `cashflow` | Доходы, расходы и чистый остаток |
| `planned_payment` | Будущие платежи и нагрузка на баланс |
| `expense_stability` | Неравномерные и крупные расходы |
| `onboarding` | Первичная настройка приложения |
| `financial_health` | Рекомендации на основе Financial Health Check |

## Статусы

| Status | Смысл |
| --- | --- |
| `new` | Создана, но ещё не показана пользователю |
| `active` | Доступна в основном списке |
| `accepted` | Пользователь принял рекомендацию |
| `hidden` | Пользователь скрыл рекомендацию |
| `snoozed` | Пользователь отложил рекомендацию |
| `expired` | Рекомендация потеряла актуальность |

## Приоритеты

```text
high
medium
low
```

Приоритет влияет на сортировку списка и важность карточки для пользователя.

## Действия пользователя

```text
view
accept
hide
snooze
refresh
```

Действия будут фиксироваться в отдельной истории событий. Это позволит измерять эффективность рекомендаций и не показывать пользователю одно и то же без причины.

## Базовые коды рекомендаций первой версии

| Code | Type | Источник |
| --- | --- | --- |
| `create_budget` | `budget` | budgets |
| `reduce_unstable_expenses` | `expense_stability` | Financial Health Check |
| `increase_savings_rate` | `saving` | Financial Health Check |
| `create_emergency_fund_goal` | `goal` | goals |
| `review_planned_payments` | `planned_payment` | planned transactions |
| `fix_cash_gap_risk` | `cashflow` | Financial Health Check |
| `complete_onboarding` | `onboarding` | onboarding |
| `check_budget_overrun` | `budget` | Financial Health Check |

## Структура карточки рекомендации

```json
{
  "id": 1,
  "code": "increase_savings_rate",
  "type": "saving",
  "priority": "medium",
  "status": "active",
  "title": "Увеличьте долю сбережений",
  "text": "После расходов остаётся слишком малая часть дохода.",
  "action": "Попробуйте откладывать хотя бы 10% дохода сразу после поступления.",
  "reason": "savingsRate.score<75",
  "source": "financial_health",
  "context": {
    "metricId": "savingsRate",
    "score": 60
  },
  "expiresAt": "2026-07-25T00:00:00Z",
  "snoozedUntil": null,
  "createdAt": "2026-06-25T00:00:00Z",
  "updatedAt": "2026-06-25T00:00:00Z"
}
```

## Параметры списка

```text
status=new|active|accepted|hidden|snoozed|expired
type=budget|saving|goal|cashflow|planned_payment|expense_stability|onboarding|financial_health
priority=high|medium|low
ordering=priority|-priority|created_at|-created_at|expires_at|-expires_at
```

## Статистика

```json
{
  "total": 12,
  "active": 5,
  "accepted": 3,
  "hidden": 2,
  "snoozed": 1,
  "expired": 1,
  "acceptanceRate": 25.0,
  "byType": {
    "budget": 3,
    "saving": 2
  },
  "byPriority": {
    "high": 4,
    "medium": 6,
    "low": 2
  }
}
```

## Ограничения первой версии

- ML не используется.
- Рекомендации не изменяют счета, операции, бюджеты и цели без явного действия пользователя.
- Повторная генерация не должна создавать дубли активных рекомендаций.
- Пользователь видит только свои рекомендации.
- A/B-тесты не реализуются полноценно на этом этапе. Для будущего расширения достаточно хранить `source`, `context` и события пользователя.

## Rule-based generator

В BUD-1159 добавлен сервис генерации рекомендаций:

```python
from apps.finance.recommendations.generator import generate_financial_recommendations

result = generate_financial_recommendations(user=request.user)
```

Генератор использует результат Financial Health Check, базовое качество данных и статус onboarding. Он создаёт или обновляет только записи `FinancialRecommendation` и события `FinancialRecommendationEvent`. Финансовые сущности пользователя не изменяются.

### Источники правил первой версии

```text
Financial Health Check recommendations
Financial Health Check dataQuality
OnboardingSurvey status
```

### Поведение при повторной генерации

- если активная рекомендация с тем же `user + code + source + source_key` уже есть, она обновляется;
- если рекомендация была скрыта или принята пользователем, генератор не создаёт её повторно;
- при создании записывается событие `created`;
- при обновлении записывается событие `refreshed`;
- рекомендации с одинаковым `code` внутри одного запуска дедуплицируются, чтобы не показывать пользователю несколько карточек с одним действием.

### Результат генерации

```json
{
  "created": 3,
  "updated": 1,
  "skipped": 0,
  "total": 4,
  "recommendationIds": [1, 2, 3, 4]
}
```

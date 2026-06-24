# Financial Health Check API contract

## Назначение

Financial Health Check оценивает финансовое состояние пользователя на основе уже существующих данных приложения: счетов, операций, бюджетов, целей и планируемых платежей. В первой версии результат не хранится в отдельной таблице, а рассчитывается по запросу.

## Endpoints будущей реализации

```http
GET /api/v1/finance/health-check/meta/
GET /api/v1/finance/health-check/summary/
```

## Метрики первой версии

| Metric ID | Назначение | Источник данных | Вес |
| --- | --- | --- | ---: |
| `incomeExpenseRatio` | Соотношение доходов и расходов | transactions | 20 |
| `savingsRate` | Доля сбережений | transactions | 18 |
| `budgetUsage` | Использование бюджетов | budgets, transactions | 18 |
| `emergencyFundProgress` | Прогресс финансовой подушки | goals | 16 |
| `cashGapRisk` | Риск кассового разрыва | accounts, planned transactions | 12 |
| `plannedPaymentsLoad` | Нагрузка планируемых платежей | planned transactions, transactions | 8 |
| `expenseStability` | Стабильность расходов | transactions | 8 |

Сумма весов равна 100. Это упрощает расчёт итогового score и делает вклад каждой метрики прозрачным.

## Уровни финансового здоровья

| Level | Score | Смысл |
| --- | --- | --- |
| `critical` | 0-39 | Высокий финансовый риск |
| `risk` | 40-59 | Есть заметные проблемы |
| `warning` | 60-74 | Требует внимания |
| `good` | 75-89 | Хорошее состояние |
| `excellent` | 90-100 | Отличное состояние |

## Параметры summary

```text
period=month|quarter|year|custom
date_from=YYYY-MM-DD
date_to=YYYY-MM-DD
currency=RUB
```

`date_from` и `date_to` обязательны только для `period=custom`. Для стандартных периодов backend может рассчитывать даты по настройкам пользователя и текущей дате.

## Структура ответа meta

```json
{
  "scoreRange": {"min": 0, "max": 100},
  "defaultPeriod": "month",
  "defaultCurrency": "RUB",
  "periods": [],
  "levels": [],
  "metrics": [],
  "recommendationPriorities": [],
  "summaryContract": {}
}
```

## Структура ответа summary

```json
{
  "score": 78,
  "level": "good",
  "period": {
    "type": "month",
    "dateFrom": "2026-06-01",
    "dateTo": "2026-06-30",
    "label": "Июнь 2026"
  },
  "metrics": [
    {
      "id": "savingsRate",
      "label": "Доля сбережений",
      "value": 18.5,
      "score": 80,
      "level": "good",
      "weight": 18,
      "unit": "percent",
      "description": "Показывает, какая часть доходов остаётся после расходов.",
      "details": {}
    }
  ],
  "recommendations": [
    {
      "code": "increase_savings_rate",
      "priority": "medium",
      "metricId": "savingsRate",
      "title": "Увеличьте долю сбережений",
      "text": "Попробуйте заранее выделять часть дохода на накопления."
    }
  ],
  "dataQuality": {
    "hasEnoughData": true,
    "transactionCount": 42,
    "periodDays": 30,
    "warnings": []
  }
}
```

## Ограничения первой версии

- Расчёт выполняется только по данным текущего пользователя.
- Endpoint не изменяет операции, счета, бюджеты или цели.
- Отдельная модель БД для результата не создаётся.
- Рекомендации являются rule-based и не используют ML.

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
      "code": "low_savings_rate",
      "priority": "medium",
      "metricId": "savingsRate",
      "title": "Низкая доля сбережений",
      "text": "После расходов остаётся слишком малая часть дохода.",
      "action": "Попробуйте откладывать хотя бы 10% дохода сразу после поступления.",
      "reason": "savingsRate.score<75"
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

## Агрегаты BUD-1152

На этапе BUD-1152 добавлен service-layer для расчёта базовых агрегированных показателей. Сервис не создаёт записи в базе и не изменяет пользовательские данные. Он только читает счета, операции, бюджеты, цели и планируемые операции текущего пользователя.

Основная функция:

```python
build_financial_health_aggregates(
    user=request.user,
    period="month",
    date_from=None,
    date_to=None,
    currency="RUB",
)
```

Возвращаемая структура агрегатов:

```json
{
  "period": {
    "type": "month",
    "dateFrom": "2026-06-01",
    "dateTo": "2026-06-23",
    "label": "Текущий месяц",
    "days": 23
  },
  "currency": "RUB",
  "totals": {
    "income": {"amount": 50000.0, "currency": "RUB"},
    "expenses": {"amount": 15000.0, "currency": "RUB"},
    "netBalance": {"amount": 35000.0, "currency": "RUB"},
    "accountsBalance": {"amount": 13000.0, "currency": "RUB"},
    "availableBalance": {"amount": 13000.0, "currency": "RUB"}
  },
  "metrics": {
    "incomeExpenseRatio": {"value": 3.3333},
    "savingsRate": {"value": 70.0},
    "budgetUsage": {"value": 60.0},
    "emergencyFundProgress": {"value": 25.0},
    "plannedPaymentsLoad": {"value": 10.0},
    "cashGapRisk": {"hasCashGapRisk": false},
    "expenseStability": {"daysWithExpenses": 2}
  },
  "dataQuality": {
    "hasEnoughData": true,
    "transactionCount": 3,
    "accountCount": 2,
    "budgetCount": 1,
    "goalCount": 1,
    "plannedTransactionCount": 1,
    "periodDays": 23,
    "warnings": []
  }
}
```

Эти агрегаты являются входными данными для следующих подзадач: расчёта общего score, уровней риска и рекомендаций.

## Расчёт score и уровней BUD-1153

На этапе BUD-1153 поверх агрегатов добавляется слой оценки финансового здоровья. Он не создаёт записи в базе и не изменяет пользовательские данные. Сервис использует агрегаты из `build_financial_health_aggregates()` и добавляет:

- индивидуальный `score` каждой метрики от 0 до 100;
- уровень каждой метрики: `critical`, `risk`, `warning`, `good`, `excellent`;
- общий взвешенный `score` от 0 до 100;
- общий уровень финансового здоровья;
- детализацию метрик с весом, описанием, значением и исходными деталями.

Основная функция:

```python
build_financial_health_summary(
    user=request.user,
    period="month",
    date_from=None,
    date_to=None,
    currency="RUB",
)
```

Пример фрагмента ответа:

```json
{
  "score": 88,
  "level": "good",
  "metrics": [
    {
      "id": "savingsRate",
      "label": "Доля сбережений",
      "value": 25.0,
      "score": 90,
      "level": "excellent",
      "weight": 18,
      "unit": "percent",
      "higherIsBetter": true,
      "details": {
        "hasPositiveCashflow": true
      }
    }
  ],
  "recommendations": [
    {
      "code": "weak_emergency_fund",
      "priority": "medium",
      "metricId": "emergencyFundProgress",
      "title": "Ускорьте накопление финансовой подушки",
      "text": "Резерв на непредвиденные расходы пока недостаточно сформирован.",
      "action": "Настройте цель накоплений и регулярно пополняйте её небольшими суммами.",
      "reason": "emergencyFundProgress.score<75"
    }
  ]
}
```

## Rule-based рекомендации BUD-1154

На этапе BUD-1154 добавлен отдельный слой rule-based рекомендаций. Он использует уже рассчитанные метрики, общий cashflow и `dataQuality`, не создаёт записи в базе и не изменяет данные пользователя.

Основная функция:

```python
build_financial_health_recommendations(
    metrics=score_payload["metrics"],
    totals=aggregates["totals"],
    data_quality=aggregates["dataQuality"],
)
```

Рекомендации формируются по понятным правилам:

| Code | Metric ID | Условие |
| --- | --- | --- |
| `insufficient_cashflow_data` | `incomeExpenseRatio` | мало операций для точной оценки |
| `negative_net_balance` | `incomeExpenseRatio` | расходы превышают доходы |
| `low_savings_rate` | `savingsRate` | score доли сбережений ниже 75 |
| `budget_over_limit` | `budgetUsage` | бюджет превышен или score бюджета ниже 70 |
| `weak_emergency_fund` | `emergencyFundProgress` | score финансовой подушки ниже 75 |
| `cash_gap_risk` | `cashGapRisk` | прогнозный доступный остаток уходит ниже нуля |
| `high_planned_payments_load` | `plannedPaymentsLoad` | score нагрузки будущих платежей ниже 65 |
| `unstable_expenses` | `expenseStability` | score стабильности расходов ниже 65 |

Каждая рекомендация содержит:

```json
{
  "code": "low_savings_rate",
  "priority": "high|medium|low",
  "metricId": "savingsRate",
  "title": "string",
  "text": "string",
  "action": "string",
  "reason": "string"
}
```

Рекомендации сортируются по приоритету и серьёзности метрики. В первой версии возвращается не больше 6 рекомендаций, чтобы ответ не был перегружен.

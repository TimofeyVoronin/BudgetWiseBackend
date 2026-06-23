# BUD-1149. Документация языка формул и API редактора

## Назначение

Документ описывает текущую backend-реализацию редактора финансовых формул для BUD-203 «API: Custom IDE For Financial Formulas».

Редактор формул позволяет frontend получать состояние IDE, сохранять один пользовательский черновик, получать справочник переменных и функций, проверять DSL-код и выполнять безопасный предпросмотр результата на финансовых данных пользователя.

Backend не выполняет пользовательский код как Python-код. Формула разбирается собственным DSL-парсером, затем выполняется только через разрешённые AST-узлы, функции, переменные, операторы и константы.

## Базовый префикс

```http
/api/v1/finance/formulas/ide/
```

Все endpoints требуют JWT-аутентификацию.

При отсутствии токена возвращается `401` в общем формате ошибок проекта.

## Состояние редактора

### Получить состояние редактора

```http
GET /api/v1/finance/formulas/ide/
```

Endpoint возвращает сохранённый черновик текущего пользователя. Если пользователь ещё не сохранял формулу, возвращается дефолтный пример без создания записи в БД.

Ответ:

```json
{
  "formula_id": "draft-default",
  "code": "RETURN start_balance + income - expenses;",
  "constructor_blocks": [
    { "id": "b1", "kind": "function", "label": "SUM" }
  ],
  "updated_at": "2026-06-13T10:00:00Z",
  "is_saved": true
}
```

Поля:

| Поле | Тип | Описание |
| ---- | --- | -------- |
| `formula_id` | string | Идентификатор черновика. В MVP всегда `draft-default`. |
| `code` | string | DSL-код формулы. |
| `constructor_blocks` | array | Состояние визуального конструктора frontend. |
| `updated_at` | string/null | Дата последнего сохранения. Для дефолтного примера может быть `null`. |
| `is_saved` | boolean | Признак того, что формула сохранена пользователем. |

### Сохранить состояние редактора

```http
PUT /api/v1/finance/formulas/ide/
```

Тело запроса:

```json
{
  "code": "RETURN start_balance + income - expenses;",
  "constructor_blocks": [
    { "id": "b1", "kind": "function", "label": "SUM" }
  ]
}
```

Ответ:

```json
{
  "formula_id": "draft-default",
  "updated_at": "2026-06-13T10:05:00Z",
  "is_saved": true
}
```

Ограничения:

- `code` не должен превышать лимит длины, заданный backend;
- `constructor_blocks` должен быть массивом объектов конструктора;
- каждый блок конструктора должен содержать `id`, `kind`, `label`;
- допустимые значения `kind`: `function`, `variable`, `operator`, `condition`;
- пользователь может работать только со своим черновиком;
- CRUD нескольких формул в MVP не реализуется.

## Метаданные редактора и автодополнения

```http
GET /api/v1/finance/formulas/ide/meta/
```

Endpoint возвращает справочник для frontend: группы переменных, функции, операторы, константы, элементы конструктора и автодополнения.

Ответ содержит:

```json
{
  "variable_groups": [],
  "constructor_variables": [],
  "constructor_operators": [],
  "autocomplete_items": []
}
```

### Группы переменных

`variable_groups` используются для палитры подсказок.

Текущие группы:

| Группа | Назначение | Элементы |
| ------ | ---------- | -------- |
| `period` | Переменные периода | `$period`, `$start_date`, `$end_date`, `$month`, `$year` |
| `accounts` | Переменные счетов | `$account`, `$accounts`, `$currency` |
| `functions` | Функции DSL | `BALANCE()`, `TRANSACTIONS()`, `SUM()`, `AVG()` |
| `operators` | Операторы | `+`, `-`, `*`, `/`, `==`, `!=`, `>`, `<`, `&&`, `||` |
| `constants` | Константы | `INCOME`, `EXPENSE`, `TRANSFER`, `TODAY()` |

### Элементы конструктора

`constructor_variables`:

| id | Название |
| -- | -------- |
| `income` | Доходы |
| `expense` | Расходы |
| `balance` | Баланс счёта |
| `budget-limit` | Лимит бюджета |

`constructor_operators`:

| id | label |
| -- | ----- |
| `plus` | `+` |
| `minus` | `-` |
| `mul` | `*` |
| `div` | `/` |
| `sum` | `SUM` |
| `avg` | `AVG` |
| `if` | `IF` |

`autocomplete_items`:

| id | name | Описание |
| -- | ---- | -------- |
| `sum` | `SUM()` | Сумма всех значений |
| `avg` | `AVG()` | Среднее значение |
| `min` | `MIN()` | Минимальное значение |
| `max` | `MAX()` | Максимальное значение |
| `count` | `COUNT()` | Количество значений |
| `if` | `IF()` | Условное выражение |
| `round` | `ROUND()` | Округление числа |

## Валидация DSL

```http
POST /api/v1/finance/formulas/ide/validate/
```

Endpoint проверяет DSL-код без выполнения формулы и без доступа к финансовым данным пользователя.

Тело запроса:

```json
{
  "code": "LET income = SUM(TRANSACTIONS(type: INCOME, date: $period)); RETURN income;"
}
```

Ответ при валидной формуле:

```json
{
  "is_valid": true,
  "errors": []
}
```

Ответ при ошибках DSL:

```json
{
  "is_valid": false,
  "errors": [
    {
      "id": "missing-return",
      "line": 1,
      "message": "В формуле должен быть оператор RETURN.",
      "severity": "error"
    }
  ]
}
```

Важно: ошибки DSL возвращаются со статусом `200`, чтобы frontend мог отображать их в панели ошибок редактора без обработки как сетевой ошибки.

Некорректное тело запроса, например отсутствие поля `code`, возвращает `400` в общем формате ошибок проекта.

## Предпросмотр выполнения формулы

```http
POST /api/v1/finance/formulas/ide/preview/
```

Endpoint сначала валидирует DSL, затем безопасно выполняет поддерживаемую часть формулы на финансовых данных текущего пользователя.

Тело запроса:

```json
{
  "code": "LET income = SUM(TRANSACTIONS(type: INCOME, date: $period)); LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period)); RETURN income - expenses;",
  "constructor_blocks": []
}
```

Ответ:

```json
{
  "rows": [
    { "id": "income", "label": "Итого доход", "value": "132 000 ₽", "highlight": false },
    { "id": "expense", "label": "Итого расход", "value": "123 600 ₽", "highlight": false },
    { "id": "net", "label": "Чистый поток", "value": "8 400 ₽", "highlight": true }
  ],
  "chart_points": [
    { "month": "Янв", "value": 33100.0 },
    { "month": "Фев", "value": 32000.0 },
    { "month": "Мар", "value": 26100.0 },
    { "month": "Апр", "value": 20400.0 },
    { "month": "Май", "value": 16000.0 },
    { "month": "Июн", "value": 8400.0 }
  ]
}
```

Поля ответа:

| Поле | Тип | Описание |
| ---- | --- | -------- |
| `rows` | array | Карточки результата для интерфейса. |
| `rows[].id` | string | Технический идентификатор строки. |
| `rows[].label` | string | Название строки. |
| `rows[].value` | string | Уже отформатированное значение с валютой. |
| `rows[].highlight` | boolean | Признак итоговой строки. |
| `chart_points` | array | Точки графика за последние месяцы. |
| `chart_points[].month` | string | Короткая подпись месяца. |
| `chart_points[].value` | number | Значение чистого потока за месяц. |

Если DSL содержит ошибку, preview возвращает `422`:

```json
{
  "detail": "В формуле найдены ошибки",
  "errors": [
    {
      "id": "division-by-zero",
      "line": 1,
      "message": "Деление на ноль в формуле.",
      "severity": "error"
    }
  ],
  "error": {
    "code": "FORMULA_VALIDATION_FAILED",
    "message": "В формуле найдены ошибки",
    "errors": [
      {
        "id": "division-by-zero",
        "line": 1,
        "message": "Деление на ноль в формуле.",
        "severity": "error"
      }
    ]
  }
}
```

Массив `errors` продублирован на верхнем уровне и внутри `error.errors`, чтобы frontend мог читать ошибки обоими способами.

## Синтаксис DSL

### Базовая структура

DSL поддерживает объявления переменных и итоговое выражение:

```text
LET <name> = <expression>;
RETURN <expression>;
```

Пример:

```text
LET income = SUM(TRANSACTIONS(type: INCOME, date: $period));
LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period));
RETURN income - expenses;
```

Требования:

- в формуле должен быть `RETURN`;
- локальные переменные объявляются через `LET`;
- локальные переменные можно использовать в последующих выражениях;
- имя локальной переменной имеет приоритет над одноимённой константой в верхнем регистре;
- инструкции завершаются `;`;
- комментарии начинаются с `//`.

## Переменные

### Системные переменные

| Переменная | Описание |
| ---------- | -------- |
| `$period` | Текущий период предпросмотра. |
| `$start_date` | Дата начала текущего периода. |
| `$end_date` | Дата окончания текущего периода. |
| `$month` | Номер текущего месяца. |
| `$year` | Год текущего периода. |
| `$account` | Текущий счёт. В MVP может быть `null`. |
| `$accounts` | Список названий активных счетов пользователя. |
| `$currency` | Валюта отображения. |

### Локальные переменные

Локальные переменные создаются через `LET`:

```text
LET net = income - expenses;
RETURN net;
```

Повторное объявление переменной считается ошибкой.

## Константы

| Константа | Описание |
| --------- | -------- |
| `INCOME` | Операции дохода. |
| `EXPENSE` | Операции расхода. |
| `TRANSFER` | Переводы. В текущем preview не используется для расчёта как отдельный тип операций. |

Константы чувствительны к смыслу регистра: `INCOME` является константой, а `income` обычно является локальной переменной.

## Функции

### TRANSACTIONS

```text
TRANSACTIONS(type: INCOME, date: $period)
```

Возвращает список сумм операций пользователя за указанный период.

Поддерживаемые именованные аргументы:

| Аргумент | Описание |
| -------- | -------- |
| `type` | Тип операции: `INCOME` или `EXPENSE`. |
| `account` | Название счёта. Если не задано, используются все счета пользователя. |
| `date` | Период или дата. Обычно `$period`, `START_OF($period)`, `END_OF($period)`. |

Позиционные аргументы не поддерживаются.

### BALANCE

```text
BALANCE(account: "Основной счёт", date: START_OF($period))
```

Возвращает баланс счёта или суммарный баланс активных счетов пользователя.

Поддерживаемые именованные аргументы:

| Аргумент | Описание |
| -------- | -------- |
| `account` | Название счёта. Если не задано, используется сумма по всем активным счетам. |
| `date` | Дата или период. В MVP используется для совместимости DSL, фактический баланс берётся из текущих данных счёта. |

Позиционные аргументы не поддерживаются.

### SUM

```text
SUM(TRANSACTIONS(type: EXPENSE, date: $period))
```

Возвращает сумму значений.

### AVG

```text
AVG(TRANSACTIONS(type: EXPENSE, date: $period))
```

Возвращает среднее значение. Если список пустой, возвращает `0`.

### COUNT

```text
COUNT(TRANSACTIONS(type: INCOME, date: $period))
```

Возвращает количество значений.

### MIN и MAX

```text
MIN(TRANSACTIONS(type: EXPENSE, date: $period))
MAX(TRANSACTIONS(type: EXPENSE, date: $period))
```

Возвращают минимальное или максимальное значение. Если список пустой, возвращают `0`.

### ROUND

```text
ROUND(income / expenses, 2)
```

Округляет число. Второй аргумент задаёт количество знаков после запятой. Допустимый диапазон: от `0` до `6`.

### IF

```text
IF(income > expenses, income - expenses, 0)
```

Условное выражение. Функция выполняется лениво: неиспользуемая ветка не вычисляется. Это значит, что выражение ниже не вызывает ошибку деления на ноль:

```text
RETURN IF(1 == 2, 100 / 0, 500);
```

### TODAY

```text
TODAY()
```

Возвращает текущую дату с учётом пользовательских настроек приложения.

### START_OF и END_OF

```text
START_OF($period)
END_OF($period)
```

Возвращают начало и конец периода.

## Операторы

Поддерживаемые операторы:

| Оператор | Назначение |
| -------- | ---------- |
| `+` | Сложение |
| `-` | Вычитание или унарный минус |
| `*` | Умножение |
| `/` | Деление |
| `==` | Равенство |
| `!=` | Неравенство |
| `>` | Больше |
| `<` | Меньше |
| `>=` | Больше или равно |
| `<=` | Меньше или равно |
| `&&` | Логическое И |
| `||` | Логическое ИЛИ |

Приоритет операторов соответствует обычной арифметике: умножение и деление выполняются раньше сложения и вычитания.

## Формат диагностик

Каждая ошибка DSL имеет формат:

```json
{
  "id": "unknown-function",
  "line": 1,
  "message": "Неизвестная функция MAGIC.",
  "severity": "error"
}
```

Поля:

| Поле | Тип | Описание |
| ---- | --- | -------- |
| `id` | string | Стабильный идентификатор ошибки. |
| `line` | integer | Номер строки, начиная с 1. |
| `message` | string | Сообщение на русском языке. |
| `severity` | string | `error` или `warning`. |

Количество диагностик ограничено, чтобы frontend не получал чрезмерно большой список ошибок.

## Основные ошибки

| id | Когда возникает |
| -- | --------------- |
| `empty-code` | Код формулы пустой. |
| `formula-too-long` | Формула превышает допустимую длину. |
| `missing-return` | В формуле отсутствует оператор `RETURN`. |
| `unknown-variable` | Используется неизвестная переменная. |
| `unknown-system-variable` | Используется неизвестная системная переменная. |
| `unknown-function` | Используется неизвестная функция. |
| `unclosed-bracket` | В вызове функции или выражении не закрыта скобка. |
| `duplicate-variable` | Переменная уже была объявлена ранее. |
| `division-by-zero` | При preview возникло деление на ноль. |
| `unknown-argument` | Передан неподдерживаемый именованный аргумент функции. |
| `invalid-function-arguments` | Некорректное количество или тип аргументов функции. |
| `invalid-transaction-type` | Тип операции не является `INCOME` или `EXPENSE`. |
| `invalid-period-argument` | Аргумент `date` нельзя использовать как период или дату. |
| `invalid-comparison` | Попытка сравнить значения разных типов. |
| `invalid-value-type` | Значение нельзя привести к числу. |
| `unsafe-construct` | Использована опасная конструкция. |
| `dunder-access-denied` | Использован идентификатор с двойным подчёркиванием. |
| `attribute-access-denied` | Использован доступ через точку. |
| `unsupported-construction` | Использована неподдерживаемая конструкция, например список или словарь. |
| `too-many-errors` | Достигнут лимит количества ошибок. |

## Ограничения безопасности

Формульный DSL не является Python-кодом. Backend запрещает:

- `eval`, `exec`, `compile`;
- `open`, `input`, `globals`, `locals`, `vars`, `dir`, `super`;
- `getattr`, `setattr`, `delattr`;
- `__import__` и другие dunder-идентификаторы;
- обращения к `os`, `sys`, `subprocess`, `pathlib`, `builtins`, `django`, `settings`;
- доступ к атрибутам через точку, например `user.password`;
- списки, словари и индексный доступ, например `[1, 2, 3]`;
- символы `` ` `` и `@`;
- произвольные функции вне whitelist;
- циклы, рекурсию, пользовательские функции, `class`, `def`, `lambda`, `try`, `while`, `for`.

Если идентификатор уже признан опасным или неподдерживаемым по правилам безопасности, backend не добавляет к нему вторичную ошибку `unknown-function` или `unknown-variable`. Это упрощает подсветку ошибок в IDE и не меняет само ограничение безопасности.

Перед выполнением preview формула проходит:

- preflight-проверку исходного кода;
- токенизацию;
- парсинг;
- проверку AST;
- runtime-guard перед вызовом функций.

## Примеры формул

### Чистый поток за текущий период

```text
LET income = SUM(TRANSACTIONS(type: INCOME, date: $period));
LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period));
RETURN income - expenses;
```

### Только доходы

```text
RETURN SUM(TRANSACTIONS(type: INCOME, date: $period));
```

### Только расходы

```text
RETURN SUM(TRANSACTIONS(type: EXPENSE, date: $period));
```

### Расходы по конкретному счёту

```text
RETURN SUM(TRANSACTIONS(account: "Основной счёт", type: EXPENSE, date: $period));
```

### Баланс счёта

```text
RETURN BALANCE(account: "Основной счёт", date: START_OF($period));
```

### Условное выражение

```text
LET income = SUM(TRANSACTIONS(type: INCOME, date: $period));
LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period));
RETURN IF(income > expenses, income - expenses, 0);
```

### Округление

```text
LET income = SUM(TRANSACTIONS(type: INCOME, date: $period));
LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period));
RETURN ROUND(income / expenses, 2);
```

## Сценарии использования frontend

### Открытие страницы редактора

1. Frontend вызывает `GET /api/v1/finance/formulas/ide/`.
2. Если `is_saved = false`, показывает дефолтный пример.
3. Frontend вызывает `GET /api/v1/finance/formulas/ide/meta/`.
4. На основе meta строятся палитра, блоки конструктора и автодополнение.

### Проверка кода в редакторе

1. Пользователь меняет код.
2. Frontend вызывает `POST /validate/`.
3. Если `is_valid = false`, ошибки отображаются в панели редактора.
4. Если `is_valid = true`, можно разрешить сохранение или preview.

### Сохранение черновика

1. Frontend сначала вызывает `POST /validate/`.
2. Если ошибок нет, отправляет `PUT /api/v1/finance/formulas/ide/`.
3. Backend сохраняет `code` и `constructor_blocks`.

### Предпросмотр

1. Frontend отправляет `POST /preview/`.
2. Если формула валидна и поддерживается evaluator, backend возвращает `rows` и `chart_points`.
3. Если формула содержит DSL-ошибки или ошибки выполнения, backend возвращает `422` с массивом `errors`.

## Ограничения MVP

В текущую реализацию не входят:

- CRUD множества пользовательских формул;
- публикация формул в отчёты;
- пользовательские функции;
- циклы и рекурсия;
- выполнение произвольного Python-кода;
- импорт внешних модулей;
- произвольный доступ к моделям Django;
- AI-генерация формул;
- сложная типизация финансовых выражений;
- полноценная историческая модель баланса на произвольную дату.

## Связанные документы

- `docs/formulas/ide_requirements.md` - требования к редактору формул и UX.
- `docs/formulas/ide_technical_design.md` - технический дизайн модели, API, parser, AST и autocomplete.

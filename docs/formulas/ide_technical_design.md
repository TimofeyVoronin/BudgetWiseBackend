# BUD-1140. Техническое проектирование редактора финансовых формул

## Назначение

Документ описывает технический дизайн backend-части для BUD-203 «API: Custom IDE For Financial Formulas». Он уточняет решения, зафиксированные в `docs/formulas/ide_requirements.md`, и переводит требования в проектную структуру: модель черновика, API-контракт, парсер, AST, автодополнение, диагностики и безопасное выполнение DSL.

Цель BUD-1140 - подготовить основу для следующих подзадач, чтобы реализация API, парсера, preview и тестов выполнялась по единому контракту.

## Границы задачи

В рамках BUD-203 реализуется MVP редактора формул. Backend поддерживает один пользовательский черновик формулы:

```text
formula_id = draft-default
```

CRUD множества формул, публикация формул в отчёты, циклы, рекурсия, пользовательские функции и AI-генерация формул в MVP не входят.

## Предлагаемая структура backend-модуля

Для реализации логики редактора формул рекомендуется использовать отдельный пакет внутри финансового приложения:

```text
apps/finance/formulas/
  __init__.py
  constants.py
  metadata.py
  diagnostics.py
  tokenizer.py
  parser.py
  ast.py
  validators.py
  evaluator.py
  services.py
  serializers.py
  views.py
```

Подключение endpoints выполняется через `apps/finance/urls.py`.

Модель черновика формулы добавляется в `apps/finance/models.py`, чтобы не создавать отдельное Django-приложение только для одного доменного объекта.

## Модель черновика формулы

Для хранения состояния редактора используется модель `FormulaIdeDraft`.

Рекомендуемые поля:

```text
FormulaIdeDraft
- id: BigAutoField
- user: OneToOneField(User, on_delete=CASCADE, related_name="formula_ide_draft")
- formula_id: CharField(max_length=64, default="draft-default")
- code: TextField
- constructor_blocks: JSONField(default=list)
- is_saved: BooleanField(default=True)
- created_at: DateTimeField(auto_now_add=True)
- updated_at: DateTimeField(auto_now=True)
```

Ограничения:

```text
- один черновик на пользователя;
- formula_id в MVP всегда draft-default;
- code не должен быть пустым при сохранении;
- constructor_blocks хранится как JSON-массив;
- данные одного пользователя не должны быть доступны другому пользователю.
```

Индексы и ограничения:

```text
UniqueConstraint(user, name="unique_formula_ide_draft_per_user")
Index(user, updated_at)
```

## API-контракт

Базовый префикс:

```text
/api/v1/finance/formulas/ide/
```

Все endpoints требуют JWT-аутентификацию.

### Получение состояния редактора

```http
GET /api/v1/finance/formulas/ide/
```

Назначение: вернуть сохранённый черновик пользователя или дефолтный пример, если черновика ещё нет.

Ответ:

```json
{
  "formula_id": "draft-default",
  "code": "RETURN income - expense;",
  "constructor_blocks": [],
  "updated_at": "2026-06-13T10:00:00Z",
  "is_saved": true
}
```

Если черновика нет, backend возвращает дефолтный пример без создания записи в БД. Запись создаётся при первом PUT.

### Сохранение состояния редактора

```http
PUT /api/v1/finance/formulas/ide/
```

Тело запроса:

```json
{
  "code": "RETURN income - expense;",
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

Перед сохранением backend повторно вызывает DSL-валидацию. Если формула содержит ошибки, возвращается HTTP 422.

### Метаданные палитры и автодополнения

```http
GET /api/v1/finance/formulas/ide/meta/
```

Назначение: вернуть справочные данные для frontend: группы переменных, функции, операторы, константы, элементы конструктора и автодополнения.

Ответ формируется из `metadata.py`. На первом этапе данные статические.

### Валидация DSL

```http
POST /api/v1/finance/formulas/ide/validate/
```

Тело запроса:

```json
{
  "code": "RETURN income - expense;"
}
```

Ответ при валидной формуле:

```json
{
  "is_valid": true,
  "errors": []
}
```

Ответ при ошибках:

```json
{
  "is_valid": false,
  "errors": [
    {
      "id": "unknown-variable",
      "line": 1,
      "message": "Неизвестная переменная budget.spent_rub.",
      "severity": "error"
    }
  ]
}
```

### Предпросмотр выполнения формулы

```http
POST /api/v1/finance/formulas/ide/preview/
```

Тело запроса:

```json
{
  "code": "RETURN income - expense;",
  "constructor_blocks": []
}
```

Ответ:

```json
{
  "rows": [
    { "id": "income", "label": "Итого доход", "value": "125 400 ₽", "highlight": false },
    { "id": "expense", "label": "Итого расход", "value": "89 200 ₽", "highlight": false },
    { "id": "net", "label": "Чистый поток", "value": "36 200 ₽", "highlight": true }
  ],
  "chart_points": [
    { "month": "Янв", "value": 12 },
    { "month": "Фев", "value": 18 },
    { "month": "Мар", "value": 15 },
    { "month": "Апр", "value": 28 },
    { "month": "Май", "value": 22 },
    { "month": "Июн", "value": 36 }
  ]
}
```

`constructor_blocks` в MVP сохраняется и возвращается, но при выполнении preview backend использует только поле `code`.

## Сервисы

Рекомендуемые сервисы:

```text
FormulaIdeDraftService
- get_or_default(user)
- save(user, code, constructor_blocks)

FormulaIdeMetadataService
- get_meta()

FormulaIdeValidationService
- validate(code) -> FormulaValidationResult

FormulaIdePreviewService
- preview(user, code, constructor_blocks=None) -> FormulaPreviewResult
```

`views.py` не должен содержать бизнес-логику. View вызывает serializer, затем соответствующий service.

## Serializer-слой

Рекомендуемые serializers:

```text
FormulaIdeStateSerializer
FormulaIdeSaveSerializer
FormulaIdeValidateSerializer
FormulaIdePreviewSerializer
FormulaIdeDiagnosticSerializer
FormulaIdeMetaSerializer или inline OpenAPI schema
```

Проверки serializer-слоя:

```text
- code обязателен для validate, save и preview;
- code не должен быть пустой строкой;
- максимальная длина code: 10 000 символов;
- constructor_blocks должен быть массивом объектов;
- kind в constructor_blocks: function, variable, operator, condition;
- label в constructor_blocks не должен быть пустым.
```

## DSL: общий формат

Минимальный формат DSL:

```text
LET <identifier> = <expression>;
RETURN <expression>;
```

Пример:

```text
LET income = SUM(TRANSACTIONS(type: INCOME, date: $period));
LET expense = SUM(TRANSACTIONS(type: EXPENSE, date: $period));
RETURN income - expense;
```

В MVP допустимы:

```text
- объявления LET;
- один обязательный RETURN;
- числовые выражения;
- строковые аргументы функций;
- именованные аргументы функций;
- вызовы разрешённых функций;
- локальные переменные, объявленные через LET;
- системные переменные с префиксом $;
- арифметические и логические операторы.
```

Не поддерживаются:

```text
- циклы;
- рекурсия;
- пользовательские функции;
- import;
- доступ к атрибутам объектов;
- произвольный Python-код;
- выполнение кода через eval/exec.
```

## Tokenizer

Tokenizer преобразует строку кода в последовательность токенов с координатами.

Токен должен содержать:

```text
- type;
- value;
- line;
- column;
- start_index;
- end_index.
```

Типы токенов:

```text
IDENTIFIER
VARIABLE
NUMBER
STRING
KEYWORD
FUNCTION
CONSTANT
OPERATOR
LPAREN
RPAREN
COMMA
COLON
SEMICOLON
EQUALS
EOF
```

Комментарии вида `// comment` игнорируются до конца строки.

## Parser и AST

Parser строит AST и возвращает список диагностик. Если синтаксис невалиден, evaluator не запускается.

Рекомендуемые AST-узлы:

```text
FormulaProgram
LetStatement
ReturnStatement
BinaryExpression
UnaryExpression
LiteralExpression
VariableExpression
FunctionCallExpression
NamedArgument
```

Пример AST для `RETURN income - expense;`:

```text
FormulaProgram
  ReturnStatement
    BinaryExpression(operator="-")
      VariableExpression(name="income")
      VariableExpression(name="expense")
```

Парсер должен учитывать приоритет операторов:

```text
1. вызовы функций и скобки
2. unary + / -
3. * и /
4. + и -
5. сравнения == != > < >= <=
6. &&
7. ||
```

## Минимальная грамматика

```text
program      := statement* return_statement EOF
statement    := let_statement
let_statement := "LET" IDENTIFIER "=" expression ";"
return_statement := "RETURN" expression ";"
expression   := logical_or
function_call := IDENTIFIER "(" argument_list? ")"
argument_list := argument ("," argument)*
argument     := IDENTIFIER ":" expression | expression
primary      := NUMBER | STRING | VARIABLE | IDENTIFIER | CONSTANT | function_call | "(" expression ")"
```

## Разрешённые переменные

Системные переменные:

```text
$period
$start_date
$end_date
$month
$year
$account
$accounts
$currency
```

Локальные переменные:

```text
LET income = ...;
LET expense = ...;
RETURN income - expense;
```

Локальная переменная доступна только после объявления. Повторное объявление переменной считается ошибкой.

## Разрешённые константы

```text
INCOME
EXPENSE
TRANSFER
```

## Разрешённые функции

Для MVP функции делятся на две группы: функции, которые должны исполняться в preview, и функции, которые могут быть доступны в meta, но возвращать понятную ошибку при отсутствии реализации.

### Обязательные для preview

```text
TRANSACTIONS(type, date, account?, category?)
SUM(values)
AVG(values)
COUNT(values)
BALANCE(account?, date?)
ROUND(value, digits?)
```

### Допустимые для последующего расширения

```text
MIN(values)
MAX(values)
IF(condition, value_if_true, value_if_false)
TODAY()
```

Если функция есть в справочнике, но пока не поддержана evaluator, backend должен вернуть DSL-ошибку `unsupported-function`, а не HTTP 500.

## Типы данных DSL

Минимальная типовая система:

```text
Number
Money
Boolean
String
Date
DateRange
TransactionSet
```

Примеры правил:

```text
TRANSACTIONS(...) -> TransactionSet
SUM(TransactionSet) -> Money
AVG(TransactionSet) -> Money
COUNT(TransactionSet) -> Number
BALANCE(...) -> Money
ROUND(Money, Number?) -> Money
income - expense -> Money
income > expense -> Boolean
```

При несовместимых типах возвращается диагностика `type-mismatch`.

## Evaluator

Evaluator выполняет только AST, построенный parser-ом. Он не использует `eval`, `exec`, `compile` или динамический импорт.

Источники данных:

```text
- Transaction;
- Account;
- Category;
- пользовательские настройки валюты, если доступны;
- текущий пользователь request.user.
```

Все запросы фильтруются по `user`.

Для preview используется период по умолчанию: последние 6 завершённых месяцев или последние 6 месяцев с учётом текущего периода, если это уже принято в проекте для аналитики. Точное правило нужно держать единым с существующими analytics-сервисами.

Форматирование денег выполняется на backend, потому что frontend-контракт ожидает готовое поле `value`, например `36 200 ₽`.

## Preview-result mapping

Даже если формула возвращает одно значение, UI ожидает rows и chart_points. Для MVP можно использовать следующий подход:

```text
rows:
- income, если формула или контекст содержит доходы;
- expense, если формула или контекст содержит расходы;
- net/result как итоговая строка.

chart_points:
- 6-12 месячных точек по результату формулы или по чистому потоку;
- month - короткая русская подпись месяца;
- value - числовое значение без форматирования.
```

Если данных нет, backend возвращает rows с нулевыми значениями и пустой или нулевой график, но не падает.

## Диагностики и ошибки

Формат диагностики:

```json
{
  "id": "unknown-variable",
  "line": 4,
  "message": "Неизвестная переменная budget.spent_rub.",
  "severity": "error"
}
```

Рекомендуемые diagnostic ids:

```text
empty-code
code-too-long
missing-return
unexpected-token
unclosed-parenthesis
unknown-variable
unknown-function
unsupported-function
duplicate-variable
invalid-let-statement
invalid-function-argument
type-mismatch
division-by-zero
unsupported-construction
execution-error
```

Для validate используется HTTP 200 даже при DSL-ошибках:

```json
{
  "is_valid": false,
  "errors": []
}
```

Для save и preview при DSL-ошибках используется HTTP 422:

```json
{
  "detail": "В формуле найдены ошибки",
  "errors": [],
  "error": {
    "code": "FORMULA_VALIDATION_FAILED",
    "message": "В формуле найдены ошибки",
    "errors": []
  }
}
```

Ошибки serializer-слоя возвращаются как HTTP 400 в общем формате проекта.

## Metadata и autocomplete

Metadata хранится в `metadata.py` как статический справочник.

Группы:

```text
period
accounts
functions
operators
constants
```

Autocomplete items должны содержать:

```text
id
name
description
insert_text или snippet, если frontend будет готов его использовать
```

Для совместимости с текущим frontend-контрактом обязательны поля:

```text
id
name
description
```

## Безопасность

Обязательные ограничения:

```text
- не использовать eval/exec;
- не выполнять Python-код из строки;
- запретить import;
- запретить доступ к атрибутам через точку;
- запретить индексирование объектов;
- запретить вызов неизвестных функций;
- ограничить длину code;
- ограничить количество LET-выражений;
- ограничить глубину вложенности AST;
- ограничить количество диагностик в ответе;
- выполнять запросы только по request.user;
- не логировать полный код формулы при ошибках, если он может содержать чувствительные данные.
```

Рекомендуемые лимиты MVP:

```text
MAX_CODE_LENGTH = 10000
MAX_STATEMENTS = 100
MAX_AST_DEPTH = 25
MAX_DIAGNOSTICS = 20
MAX_PREVIEW_MONTHS = 12
```

## OpenAPI

Для views нужно добавить `extend_schema` с тегом:

```text
finance-formula-ide
```

Минимально документируются:

```text
GET /finance/formulas/ide/
PUT /finance/formulas/ide/
GET /finance/formulas/ide/meta/
POST /finance/formulas/ide/validate/
POST /finance/formulas/ide/preview/
```

`docs/openapi/schema.yaml` не включается в архивы с изменениями. Пользователь обновляет схему локально после проверки.

## План реализации по следующим подзадачам

### BUD-1141

Реализовать модель черновика, serializers, meta service, GET/PUT состояния редактора и meta endpoint.

### BUD-1142

Реализовать tokenizer, parser, AST, базовые диагностики и проверку `LET` / `RETURN`.

### BUD-1143

Реализовать validate endpoint и согласованный формат ответа `is_valid/errors`.

### BUD-1144

Реализовать evaluator и preview endpoint, который возвращает `rows` и `chart_points`.

### BUD-1145

Закрыть ошибки и граничные случаи: пустой код, слишком длинный код, деление на ноль, unsupported functions, отсутствующие данные.

### BUD-1146

Усилить ограничения безопасности и добавить проверки запрета опасных конструкций.

### BUD-1147

Оптимизировать запросы к БД и справочники metadata.

### BUD-1148

Добавить тесты API, parser, diagnostics, evaluator, auth, user isolation и security restrictions.

### BUD-1149

Описать язык формул, функции, переменные, примеры и ограничения.

### BUD-1150

Провести code review и рефакторинг.

## Acceptance criteria

BUD-1140 считается выполненной, если:

```text
- описана модель черновика формулы;
- зафиксирована структура backend-модуля;
- описан API-контракт;
- описан tokenizer/parser/AST;
- описаны функции, переменные, операторы и типы DSL;
- описан формат diagnostics;
- описан metadata/autocomplete contract;
- зафиксированы ограничения безопасности;
- следующие подзадачи можно реализовывать без пересмотра общей архитектуры.
```

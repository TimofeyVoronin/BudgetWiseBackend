# API Error Contract

Документ описывает единый формат ошибок backend API проекта BudgetWiseBackend.

Цель документа - зафиксировать структуру error response, чтобы frontend мог одинаково обрабатывать ошибки валидации, авторизации, доступа, конфликтов данных и внутренних ошибок сервера.

## Общий формат ошибки

Все ошибки API возвращаются в едином формате:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "validation_error",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "field": [
        "Описание ошибки."
      ]
    },
    "detail": null,
    "trace_id": null
  }
}
```

## Назначение полей

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `success` | boolean | Да | Для ошибок всегда `false` |
| `error` | object | Да | Объект с информацией об ошибке |
| `error.status_code` | integer | Да | HTTP-код ответа |
| `error.code` | string | Да | Машиночитаемый код ошибки |
| `error.message` | string | Да | Короткое сообщение для frontend или пользователя |
| `error.field_errors` | object или null | Нет | Ошибки конкретных полей при валидации |
| `error.detail` | object, array, string или null | Нет | Дополнительная информация об ошибке |
| `error.trace_id` | string или null | Нет | Идентификатор ошибки для поиска в логах |

## Общие правила

- Все ошибки проходят через глобальный обработчик `custom_exception_handler`.
- Ошибки валидации возвращаются со статусом `400`.
- Ошибки доступа возвращаются со статусами `401` или `403`.
- Если объект не найден или не принадлежит текущему пользователю, возвращается `404`.
- Конфликт бизнес-правил возвращается как `409`.
- Непредвиденные ошибки возвращаются как `500`.
- Для `500` генерируется `trace_id`.
- Для обычных клиентских ошибок `trace_id` может быть `null`.
- Критические ошибки логируются со stack trace.
- Клиентские ошибки логируются как `WARNING` с контекстом запроса.

## Типовые error codes

| HTTP-код | `error.code` | Когда используется |
|---|---|---|
| `400` | `validation_error` | Общая ошибка валидации |
| `400` | `invalid` | Некорректное значение поля или query-параметра |
| `400` | `unique` | Нарушение уникальности данных |
| `400` | `business_rule_error` | Нарушение бизнес-правила |
| `401` | `not_authenticated` | Не передан access token |
| `401` | `authentication_failed` | Передан некорректный access token |
| `403` | `permission_denied` | Недостаточно прав |
| `404` | `not_found` | Объект не найден |
| `405` | `method_not_allowed` | HTTP-метод не разрешён |
| `409` | `conflict` | Конфликт состояния данных |
| `409` | `category_has_children` | Категорию нельзя удалить из-за дочерних категорий |
| `409` | `category_has_transactions` | Категорию нельзя удалить, потому что она используется в операциях |
| `409` | `category_has_budgets` | Категорию нельзя удалить, потому что она используется в бюджетах |
| `409` | `integrity_error` | Нарушено ограничение целостности данных |
| `409` | `protected_object` | Объект защищён связанными данными |
| `500` | `server_error` | Внутренняя ошибка сервера |

## Пример 400: ошибка query-параметра

Запрос:

```http
GET /api/v1/users/?is_staff=wrong
Authorization: Bearer <admin_access_token>
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "invalid",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "is_staff": "Параметр должен быть boolean: true или false."
    },
    "detail": null,
    "trace_id": null
  }
}
```

## Пример 400: ошибка данных операции

Запрос:

```http
POST /api/v1/finance/transactions/
Authorization: Bearer <access_token>
Content-Type: application/json
```

Тело запроса:

```json
{
  "account": 1,
  "category": 1,
  "type": "expense",
  "amount": "100.00",
  "description": "Некорректная операция",
  "operation_date": "2026-05-10"
}
```

Если категория имеет тип `income`, а операция имеет тип `expense`, backend вернёт ошибку:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "invalid",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "category": [
        "Тип категории должен совпадать с типом операции."
      ]
    },
    "detail": null,
    "trace_id": null
  }
}
```

## Пример 400: ошибка уникальности пользователя

Запрос:

```http
POST /api/v1/users/
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

Тело запроса:

```json
{
  "username": "new_user",
  "email": "demo@example.com",
  "password": "strong-password-123",
  "first_name": "New",
  "last_name": "User",
  "is_active": true,
  "is_staff": false,
  "is_superuser": false
}
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "unique",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "email": [
        "Пользователь с таким email уже существует."
      ]
    },
    "detail": null,
    "trace_id": null
  }
}
```

## Пример 401: пользователь не авторизован

Запрос:

```http
GET /api/v1/finance/categories/
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "code": "not_authenticated",
    "message": "Пользователь не авторизован.",
    "field_errors": null,
    "detail": "Учетные данные не были предоставлены.",
    "trace_id": null
  }
}
```

## Пример 401: некорректный заголовок авторизации

Запрос:

```http
GET /api/v1/users/?is_staff=wrong
Authorization: Bearer
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "code": "authentication_failed",
    "message": "Пользователь не авторизован.",
    "field_errors": null,
    "detail": {
      "detail": "Заголовок авторизации должен содержать два значения, разделенных пробелом",
      "code": "bad_authorization_header"
    },
    "trace_id": null
  }
}
```

## Пример 403: недостаточно прав

Запрос:

```http
GET /api/v1/users/
Authorization: Bearer <regular_user_access_token>
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 403,
    "code": "permission_denied",
    "message": "Недостаточно прав для выполнения действия.",
    "field_errors": null,
    "detail": "У вас недостаточно прав для выполнения данного действия.",
    "trace_id": null
  }
}
```

## Пример 404: объект не найден

Запрос:

```http
GET /api/v1/users/999999/
Authorization: Bearer <admin_access_token>
```

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 404,
    "code": "not_found",
    "message": "Объект не найден.",
    "field_errors": null,
    "detail": "Страница не найдена.",
    "trace_id": null
  }
}
```

Важно: если объект принадлежит другому пользователю, backend также может вернуть `404`, чтобы не раскрывать наличие чужих данных.

## Пример 409: конфликт при удалении категории

Запрос:

```http
DELETE /api/v1/finance/categories/3/
Authorization: Bearer <access_token>
```

Если категория используется в операциях, backend вернёт:

```json
{
  "success": false,
  "error": {
    "status_code": 409,
    "code": "category_has_transactions",
    "message": "Категорию нельзя удалить, так как она используется в операциях.",
    "field_errors": null,
    "detail": null,
    "trace_id": null
  }
}
```

## Пример 500: внутренняя ошибка сервера

Ответ:

```json
{
  "success": false,
  "error": {
    "status_code": 500,
    "code": "server_error",
    "message": "Внутренняя ошибка сервера.",
    "field_errors": null,
    "detail": null,
    "trace_id": "6b1d9d5c-1d2a-4e55-9f8d-33c6c9f5f100"
  }
}
```

Для `500` frontend не должен показывать пользователю технические детали. Можно показать общее сообщение и `trace_id`.

Пример текста:

```text
Произошла внутренняя ошибка. Код обращения: 6b1d9d5c-1d2a-4e55-9f8d-33c6c9f5f100.
```

## Trace ID

`trace_id` нужен для связи ответа API с записью в логах.

Правила:

- для обычных клиентских ошибок `trace_id` может быть `null`;
- для ошибок `500` `trace_id` должен быть заполнен;
- если клиент передал заголовок `X-Request-ID`, backend может использовать его как `trace_id`;
- если клиент передал заголовок `X-Correlation-ID`, backend может использовать его как `trace_id`;
- `trace_id` логируется вместе с ошибкой.

## Логирование ошибок

Клиентские ошибки `4xx` логируются на уровне `WARNING`.

Пример:

```text
API client error. status_code=400 code=invalid message=Некорректные данные запроса. trace_id=None method=GET path=/api/v1/users/ query_params={'is_staff': 'wrong'} user_id=72 client_ip=127.0.0.1
```

Серверные ошибки `5xx` логируются на уровне `ERROR` со stack trace.

В логах фиксируются:

- `status_code`;
- `code`;
- `message`;
- `trace_id`;
- HTTP method;
- path;
- query params;
- user id;
- client ip.

## Требования к frontend

Frontend должен:

- проверять `success`;
- читать `error.status_code`;
- использовать `error.code` для выбора логики обработки;
- показывать пользователю `error.message`;
- использовать `error.field_errors` для подсветки полей формы;
- не показывать технический `detail`, если он не предназначен для интерфейса;
- передавать `trace_id` разработчику при обращении за поддержкой.

## Требования к backend

Backend должен:

- возвращать ошибки только в едином формате;
- не отдавать traceback пользователю;
- не раскрывать лишнюю информацию о чужих объектах;
- использовать понятные `code`;
- логировать ошибки с контекстом;
- добавлять `trace_id` для серверных ошибок;
- покрывать основные негативные сценарии автотестами.

## Публичные endpoints

Следующие endpoints доступны без JWT:

```text
GET /health/
GET /api/v1/
GET /api/schema/
GET /api/docs/
```

Защищённые endpoints требуют заголовок:

```http
Authorization: Bearer <access_token>
```

## Ключевые endpoints и типовые ошибки

| Endpoint | Возможные ошибки |
|---|---|
| `GET /api/v1/finance/categories/` | `401`, `400` при некорректных query-параметрах |
| `POST /api/v1/finance/categories/` | `401`, `400`, `409` |
| `PATCH /api/v1/finance/categories/{id}/` | `401`, `400`, `404`, `409` |
| `DELETE /api/v1/finance/categories/{id}/` | `401`, `404`, `409` |
| `GET /api/v1/finance/transactions/` | `401`, `400` при некорректных query-параметрах |
| `POST /api/v1/finance/transactions/` | `401`, `400`, `404` |
| `PATCH /api/v1/finance/transactions/{id}/` | `401`, `400`, `404` |
| `DELETE /api/v1/finance/transactions/{id}/` | `401`, `404` |
| `GET /api/v1/users/me/` | `401` |
| `PATCH /api/v1/users/me/` | `401`, `400` |
| `GET /api/v1/users/` | `401`, `403`, `400` |
| `POST /api/v1/users/` | `401`, `403`, `400` |
| `PATCH /api/v1/users/{id}/` | `401`, `403`, `400`, `404` |
| `DELETE /api/v1/users/{id}/` | `401`, `403`, `400`, `404` |
# API Contract

Документ описывает предварительный контракт REST API backend-части приложения BudgetWise.

Текущая версия API:

```text
v1
```

Базовый префикс API:

```text
/api/v1/
```

## Общие принципы

Backend предоставляет REST API для frontend-приложения. Большинство endpoints требуют JWT-аутентификацию.

Для защищённых запросов используется заголовок:

```http
Authorization: Bearer <access_token>
```

Формат данных:

```text
JSON
```

Основные HTTP-коды:

| Код | Значение |
|---|---|
| `200 OK` | Успешный запрос |
| `201 Created` | Объект успешно создан |
| `204 No Content` | Объект успешно удалён |
| `400 Bad Request` | Ошибка валидации или некорректный запрос |
| `401 Unauthorized` | Пользователь не авторизован |
| `403 Forbidden` | Недостаточно прав |
| `404 Not Found` | Объект не найден |
| `409 Conflict` | Конфликт состояния данных, например попытка удалить объект со связанными записями |
| `500 Internal Server Error` | Внутренняя ошибка сервера |

## Формат ошибки

Для ошибок используется единый формат ответа:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "field": [
        "Error message"
      ]
    }
  }
}
```

Для ошибок без привязки к конкретному полю поле `detail` может содержать строку или объект.

Пример ошибки авторизации:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "detail": {
      "detail": "Authentication credentials were not provided."
    }
  }
}
```

Пример ошибки валидации:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "amount": [
        "Ensure this value is greater than 0."
      ]
    }
  }
}
```

## Пагинация

Для списков используется пагинация.

Параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы, максимум 100 |

Базовый размер страницы:

```text
20
```

Ожидаемый формат пагинированного ответа Django REST Framework:

```json
{
  "count": 100,
  "next": "http://127.0.0.1:8000/api/v1/finance/transactions/?page=2",
  "previous": null,
  "results": []
}
```

## Соответствие API и ORM-моделей

API-контракт синхронизирован с текущими ORM-моделями финансового модуля.

| API resource | ORM model | Назначение |
|---|---|---|
| `/api/v1/users/me/` | `User` | Данные текущего пользователя |
| `/api/v1/finance/accounts/` | `Account` | Счета пользователя |
| `/api/v1/finance/categories/` | `Category` | Категории доходов и расходов |
| `/api/v1/finance/transactions/` | `Transaction` | Финансовые операции |
| `/api/v1/finance/budgets/` | `Budget` | Бюджеты по категориям и периодам |
| `/api/v1/finance/goals/` | `Goal` | Финансовые цели |
| `/api/v1/finance/reports/summary/` | `Transaction`, `Account`, `Category` | Расчётная финансовая сводка |

Все основные финансовые сущности связаны с пользователем через поле `user`.

Пользователь может работать только со своими финансовыми данными. Это правило должно соблюдаться на уровне queryset, serializers, services и permission-проверок.

Основные типы данных:

| Тип в API | Тип в ORM | Пример |
|---|---|---|
| `integer` | `BigAutoField`, `ForeignKey` | `1` |
| `string` | `CharField`, `TextField` | `"Основная карта"` |
| `decimal` | `DecimalField(max_digits=14, decimal_places=2)` | `"1200.00"` |
| `boolean` | `BooleanField` | `true` |
| `date` | `DateField` | `"2026-05-07"` |
| `datetime` | `DateTimeField` | `"2026-05-07T10:30:00+00:00"` |

Денежные значения передаются строкой, чтобы избежать ошибок округления на стороне клиента.

## Текущие служебные endpoints

### Health-check

| Поле | Значение |
|---|---|
| URL | `/health/` |
| Метод | `GET` |
| Доступ | Публичный |
| Статус | Реализовано |

Назначение: проверка состояния backend-сервиса.

Параметры запроса отсутствуют.

Основные поля ответа:

| Поле | Тип | Описание |
|---|---|---|
| `status` | string | Состояние сервиса |
| `service` | string | Название сервиса |
| `version` | string | Версия API или приложения |
| `timestamp` | string | Время ответа сервера в ISO-формате |

Пример запроса:

```http
GET /health/ HTTP/1.1
Host: 127.0.0.1:8000
```

Пример успешного ответа:

```json
{
  "status": "ok",
  "service": "BudgetWiseBackend",
  "version": "1.0.0",
  "timestamp": "2026-05-06T22:44:44.084816+00:00"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Сервис доступен |

---

### API root

| Поле | Значение |
|---|---|
| URL | `/api/v1/` |
| Метод | `GET` |
| Доступ | Публичный |
| Статус | Реализовано |

Назначение: корневой endpoint API версии `v1`.

Параметры запроса отсутствуют.

Основные поля ответа:

| Поле | Тип | Описание |
|---|---|---|
| `service` | string | Название API |
| `version` | string | Текущая версия API |
| `endpoints` | object | Список основных маршрутов |

Пример запроса:

```http
GET /api/v1/ HTTP/1.1
Host: 127.0.0.1:8000
```

Пример успешного ответа:

```json
{
  "service": "BudgetWiseBackend API",
  "version": "v1",
  "endpoints": {
    "users": "/api/v1/users/",
    "finance": "/api/v1/finance/",
    "schema": "/api/schema/",
    "docs": "/api/docs/",
    "health": "/health/"
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Endpoint доступен |

---

### OpenAPI schema

| Поле | Значение |
|---|---|
| URL | `/api/schema/` |
| Метод | `GET` |
| Доступ | Публичный |
| Статус | Реализовано |

Назначение: получение OpenAPI-схемы.

Пример запроса:

```http
GET /api/schema/ HTTP/1.1
Host: 127.0.0.1:8000
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Схема успешно сформирована |

---

### Swagger UI

| Поле | Значение |
|---|---|
| URL | `/api/docs/` |
| Метод | `GET` |
| Доступ | Публичный |
| Статус | Реализовано |

Назначение: просмотр Swagger-документации API.

Пример запроса:

```http
GET /api/docs/ HTTP/1.1
Host: 127.0.0.1:8000
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Документация доступна |

## Auth endpoints

Endpoints аутентификации будут использовать JWT.

### Регистрация пользователя

| Поле | Значение |
|---|---|
| URL | `/api/v1/auth/register/` |
| Метод | `POST` |
| Доступ | Публичный |
| Статус | Планируется |

Назначение: создание нового пользователя.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `username` | string | Да | Имя пользователя |
| `email` | string | Да | Email пользователя |
| `password` | string | Да | Пароль |
| `password_confirm` | string | Да | Подтверждение пароля |

Пример запроса:

```http
POST /api/v1/auth/register/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json
```

```json
{
  "username": "timofey",
  "email": "timofey@example.com",
  "password": "StrongPassword123",
  "password_confirm": "StrongPassword123"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "username": "timofey",
  "email": "timofey@example.com"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "email": [
        "User with this email already exists."
      ],
      "password_confirm": [
        "Passwords do not match."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Пользователь создан |
| `400` | Ошибка валидации |

---

### Получение JWT-токенов

| Поле | Значение |
|---|---|
| URL | `/api/v1/auth/token/` |
| Метод | `POST` |
| Доступ | Публичный |
| Статус | Планируется |

Назначение: получение access и refresh токенов.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `username` | string | Да | Имя пользователя |
| `password` | string | Да | Пароль |

Пример запроса:

```http
POST /api/v1/auth/token/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json
```

```json
{
  "username": "timofey",
  "password": "StrongPassword123"
}
```

Пример успешного ответа:

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.access",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.refresh"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "detail": {
      "detail": "No active account found with the given credentials"
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Токены получены |
| `401` | Неверные учетные данные |

---

### Обновление JWT-токена

| Поле | Значение |
|---|---|
| URL | `/api/v1/auth/token/refresh/` |
| Метод | `POST` |
| Доступ | Публичный |
| Статус | Планируется |

Назначение: получение нового access token по refresh token.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `refresh` | string | Да | Refresh token |

Пример запроса:

```http
POST /api/v1/auth/token/refresh/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json
```

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.refresh"
}
```

Пример успешного ответа:

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new_access",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new_refresh"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "detail": {
      "detail": "Token is invalid or expired",
      "code": "token_not_valid"
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Токен обновлён |
| `401` | Refresh token недействителен |

## Users endpoints

### Получение текущего пользователя

| Поле | Значение |
|---|---|
| URL | `/api/v1/users/me/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение данных текущего пользователя.

Параметры запроса отсутствуют.

Пример запроса:

```http
GET /api/v1/users/me/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "id": 1,
  "username": "timofey",
  "email": "timofey@example.com",
  "first_name": "Timofey",
  "last_name": ""
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "detail": {
      "detail": "Authentication credentials were not provided."
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Данные пользователя получены |
| `401` | Пользователь не авторизован |

## Finance endpoints

### Список счетов

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка счетов текущего пользователя.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `is_active` | boolean | Нет | Фильтр по активности счёта |

Пример запроса:

```http
GET /api/v1/finance/accounts/?page=1&page_size=20&is_active=true HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Основная карта",
      "balance": "25000.00",
      "currency": "RUB",
      "is_active": true,
      "created_at": "2026-05-07T10:00:00+00:00"
    },
    {
      "id": 2,
      "name": "Наличные",
      "balance": "5000.00",
      "currency": "RUB",
      "is_active": true,
      "created_at": "2026-05-07T10:05:00+00:00"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список счетов получен |
| `401` | Пользователь не авторизован |

---

### Создание счёта

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание нового счёта пользователя.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `name` | string | Да | Название счёта |
| `balance` | decimal | Нет | Начальный баланс |
| `currency` | string | Да | Валюта счёта |

Пример запроса:

```http
POST /api/v1/finance/accounts/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Основная карта",
  "balance": "25000.00",
  "currency": "RUB"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "name": "Основная карта",
  "balance": "25000.00",
  "currency": "RUB",
  "is_active": true,
  "created_at": "2026-05-07T10:00:00+00:00"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "name": [
        "This field is required."
      ],
      "currency": [
        "This field is required."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Счёт создан |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |

---

### Получение, обновление и удаление счёта

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: работа с конкретным счётом пользователя.

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID счёта |

Пример запроса на получение:

```http
GET /api/v1/finance/accounts/1/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "id": 1,
  "name": "Основная карта",
  "balance": "25000.00",
  "currency": "RUB",
  "is_active": true,
  "created_at": "2026-05-07T10:00:00+00:00"
}
```

Пример запроса на частичное обновление:

```http
PATCH /api/v1/finance/accounts/1/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Зарплатная карта"
}
```

Пример успешного ответа после обновления:

```json
{
  "id": 1,
  "name": "Зарплатная карта",
  "balance": "25000.00",
  "currency": "RUB",
  "is_active": true,
  "created_at": "2026-05-07T10:00:00+00:00"
}
```

Пример ошибки доступа:

```json
{
  "success": false,
  "error": {
    "status_code": 403,
    "detail": {
      "detail": "You do not have permission to perform this action."
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Счёт получен или обновлён |
| `204` | Счёт удалён |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к счёту |
| `404` | Счёт не найден |
| `409` | Категория не может быть удалена, так как с ней связаны операции или бюджеты |

Если у счёта есть связанные операции, физическое удаление должно быть запрещено. В таком случае frontend может использовать частичное обновление и передать `is_active=false`, чтобы скрыть счёт без потери истории операций.

Если категория используется в операциях или бюджетах, физическое удаление должно быть запрещено. В таком случае рекомендуется использовать `PATCH` с `is_active=false`, чтобы сохранить историю финансовых данных.

---

### Список категорий

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка категорий доходов и расходов.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `type` | string | Нет | Тип категории: `income` или `expense` |
| `is_active` | boolean | Нет | Фильтр по активности категории |

Пример запроса:

```http
GET /api/v1/finance/categories/?type=expense&is_active=true HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Продукты",
      "type": "expense",
      "is_active": true,
      "created_at": "2026-05-07T10:10:00+00:00"
    },
    {
      "id": 2,
      "name": "Транспорт",
      "type": "expense",
      "is_active": true,
      "created_at": "2026-05-07T10:15:00+00:00"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список категорий получен |
| `401` | Пользователь не авторизован |

---

### Создание категории

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание категории доходов или расходов.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `name` | string | Да | Название категории |
| `type` | string | Да | Тип категории: `income` или `expense` |

Пример запроса:

```http
POST /api/v1/finance/categories/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Продукты",
  "type": "expense"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "name": "Продукты",
  "type": "expense",
  "is_active": true,
  "created_at": "2026-05-07T10:10:00+00:00"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "type": [
        "Value must be one of: income, expense."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Категория создана |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |

---

### Получение, обновление и удаление категории

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: работа с конкретной категорией пользователя.

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID категории |

Пример запроса:

```http
GET /api/v1/finance/categories/1/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "id": 1,
  "name": "Продукты",
  "type": "expense",
  "is_active": true,
  "created_at": "2026-05-07T10:10:00+00:00"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Категория получена или обновлена |
| `204` | Категория удалена |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к категории |
| `404` | Категория не найдена |

---

## Budget endpoints

### Список бюджетов

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка бюджетов текущего пользователя.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `category` | integer | Нет | Фильтр по категории |
| `is_active` | boolean | Нет | Фильтр по активности бюджета |
| `period_start` | date | Нет | Начало периода |
| `period_end` | date | Нет | Конец периода |

Пример успешного ответа:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "category": 1,
      "amount_limit": "25000.00",
      "period_start": "2026-05-01",
      "period_end": "2026-05-31",
      "is_active": true,
      "created_at": "2026-05-07T10:00:00+00:00",
      "updated_at": "2026-05-07T10:00:00+00:00"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список бюджетов получен |
| `401` | Пользователь не авторизован |

---

### Создание бюджета

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание бюджета по категории расходов за период.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `category` | integer | Да | ID категории расходов |
| `amount_limit` | decimal | Да | Лимит бюджета |
| `period_start` | date | Да | Начало периода |
| `period_end` | date | Да | Конец периода |
| `is_active` | boolean | Нет | Активен ли бюджет |

Пример запроса:

```json
{
  "category": 1,
  "amount_limit": "25000.00",
  "period_start": "2026-05-01",
  "period_end": "2026-05-31",
  "is_active": true
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "category": 1,
  "amount_limit": "25000.00",
  "period_start": "2026-05-01",
  "period_end": "2026-05-31",
  "is_active": true,
  "created_at": "2026-05-07T10:00:00+00:00",
  "updated_at": "2026-05-07T10:00:00+00:00"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "amount_limit": [
        "Ensure this value is greater than 0."
      ],
      "period_end": [
        "Дата окончания периода не может быть раньше даты начала."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Бюджет создан |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к категории |

---

### Получение, обновление и удаление бюджета

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID бюджета |

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Бюджет получен или обновлён |
| `204` | Бюджет удалён |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к бюджету |
| `404` | Бюджет не найден |

## Goal endpoints

### Список финансовых целей

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка финансовых целей текущего пользователя.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `status` | string | Нет | Статус цели: `active`, `completed`, `cancelled` |
| `account` | integer | Нет | Фильтр по связанному счёту |

Пример успешного ответа:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "account": 3,
      "name": "Финансовая подушка",
      "target_amount": "300000.00",
      "current_amount": "150000.00",
      "deadline": null,
      "status": "active",
      "created_at": "2026-05-07T10:00:00+00:00",
      "updated_at": "2026-05-07T10:00:00+00:00"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список целей получен |
| `401` | Пользователь не авторизован |

---

### Создание финансовой цели

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание финансовой цели пользователя.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `account` | integer | Нет | ID связанного счёта |
| `name` | string | Да | Название цели |
| `target_amount` | decimal | Да | Целевая сумма |
| `current_amount` | decimal | Нет | Текущая накопленная сумма |
| `deadline` | date | Нет | Желаемая дата достижения |
| `status` | string | Нет | Статус цели |

Пример запроса:

```json
{
  "account": 3,
  "name": "Финансовая подушка",
  "target_amount": "300000.00",
  "current_amount": "150000.00",
  "deadline": null,
  "status": "active"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "account": 3,
  "name": "Финансовая подушка",
  "target_amount": "300000.00",
  "current_amount": "150000.00",
  "deadline": null,
  "status": "active",
  "created_at": "2026-05-07T10:00:00+00:00",
  "updated_at": "2026-05-07T10:00:00+00:00"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "target_amount": [
        "Ensure this value is greater than 0."
      ],
      "current_amount": [
        "Ensure this value is greater than or equal to 0."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Цель создана |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к связанному счёту |

---

### Получение, обновление и удаление финансовой цели

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID цели |

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Цель получена или обновлена |
| `204` | Цель удалена |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к цели |
| `404` | Цель не найдена |

### Список операций

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/transactions/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка финансовых операций пользователя.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `account` | integer | Нет | Фильтр по счёту |
| `category` | integer | Нет | Фильтр по категории |
| `type` | string | Нет | Тип операции: `income` или `expense` |
| `date_from` | string | Нет | Начало периода |
| `date_to` | string | Нет | Конец периода |
| `ordering` | string | Нет | Сортировка, например `operation_date` или `-operation_date` |

Пример запроса:

```http
GET /api/v1/finance/transactions/?account=1&type=expense&date_from=2026-05-01&date_to=2026-05-31&ordering=-operation_date HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "account": 1,
      "category": 1,
      "type": "expense",
      "amount": "1200.00",
      "description": "Покупка продуктов",
      "operation_date": "2026-05-07",
      "created_at": "2026-05-07T10:30:00+00:00"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список операций получен |
| `400` | Некорректные параметры фильтрации |
| `401` | Пользователь не авторизован |

---

### Создание операции

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/transactions/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание новой финансовой операции.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `account` | integer | Да | ID счёта |
| `category` | integer | Да | ID категории |
| `type` | string | Да | Тип операции: `income` или `expense` |
| `amount` | decimal | Да | Сумма операции |
| `description` | string | Нет | Описание операции |
| `operation_date` | string | Да | Дата операции |

Пример запроса:

```http
POST /api/v1/finance/transactions/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "account": 1,
  "category": 1,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов",
  "operation_date": "2026-05-07"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "account": 1,
  "category": 1,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+00:00"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "amount": [
        "Ensure this value is greater than 0."
      ],
      "operation_date": [
        "Date has wrong format. Use YYYY-MM-DD."
      ]
    }
  }
}
```

Пример ошибки доступа:

```json
{
  "success": false,
  "error": {
    "status_code": 403,
    "detail": {
      "detail": "You do not have permission to use this account."
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Операция создана |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к счёту или категории |

---

### Получение, обновление и удаление операции

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/transactions/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: работа с конкретной финансовой операцией.

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID операции |

Пример запроса на получение:

```http
GET /api/v1/finance/transactions/1/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "id": 1,
  "account": 1,
  "category": 1,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+00:00"
}
```

Пример запроса на частичное обновление:

```http
PATCH /api/v1/finance/transactions/1/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "description": "Покупка продуктов и бытовых товаров"
}
```

Пример успешного ответа после обновления:

```json
{
  "id": 1,
  "account": 1,
  "category": 1,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов и бытовых товаров",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+00:00"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Операция получена или обновлена |
| `204` | Операция удалена |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Нет доступа к операции |
| `404` | Операция не найдена |

## Reports endpoints

### Краткий финансовый отчёт

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/reports/summary/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение краткой сводки по доходам, расходам и балансу за выбранный период.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `date_from` | string | Нет | Начало периода |
| `date_to` | string | Нет | Конец периода |
| `account` | integer | Нет | Фильтр по счёту |

Пример запроса:

```http
GET /api/v1/finance/reports/summary/?date_from=2026-05-01&date_to=2026-05-31&account=1 HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "income_total": "80000.00",
  "expense_total": "32500.00",
  "balance_delta": "47500.00",
  "period": {
    "date_from": "2026-05-01",
    "date_to": "2026-05-31"
  }
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "detail": {
      "date_to": [
        "date_to must be greater than or equal to date_from."
      ]
    }
  }
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Отчёт сформирован |
| `400` | Некорректные параметры периода |
| `401` | Пользователь не авторизован |
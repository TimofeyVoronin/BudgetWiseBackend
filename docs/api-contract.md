# API Contract

Документ описывает контракт REST API backend-части приложения BudgetWiseBackend.

Текущая версия API:

```text
v1
```

Базовый префикс API:

```text
/api/v1/
```

## Общие принципы

Backend предоставляет REST API для frontend-приложения. Основные endpoints защищены JWT-аутентификацией.

Для защищённых запросов используется заголовок:

```http
Authorization: Bearer <access_token>
```

Формат данных:

```text
JSON
```

Публичные endpoints:

```text
GET /health/
GET /api/v1/
GET /api/schema/
GET /api/docs/
```

Защищённые endpoints:

```text
/api/v1/users/
/api/v1/users/me/
/api/v1/finance/categories/
/api/v1/finance/transactions/
```

## Основные HTTP-коды

| Код | Значение |
|---|---|
| `200 OK` | Успешный запрос |
| `201 Created` | Объект успешно создан |
| `204 No Content` | Объект успешно удалён или деактивирован без тела ответа |
| `400 Bad Request` | Ошибка валидации или некорректный запрос |
| `401 Unauthorized` | Пользователь не авторизован |
| `403 Forbidden` | Недостаточно прав |
| `404 Not Found` | Объект не найден |
| `405 Method Not Allowed` | HTTP-метод не разрешён |
| `409 Conflict` | Конфликт состояния данных |
| `500 Internal Server Error` | Внутренняя ошибка сервера |

## Формат ошибки API

Backend использует единый формат ошибок для всех endpoints.

Подробный контракт ошибок, список error codes и примеры ответов описаны в отдельном документе:

```text
docs/api-errors.md
```

Базовый формат ошибки:

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

Назначение полей:

| Поле | Тип | Описание |
|---|---|---|
| `success` | boolean | Для ошибок всегда `false` |
| `error.status_code` | integer | HTTP-код ответа |
| `error.code` | string | Машиночитаемый код ошибки |
| `error.message` | string | Короткое сообщение для frontend или пользователя |
| `error.field_errors` | object или null | Ошибки конкретных полей |
| `error.detail` | object, array, string или null | Дополнительная информация |
| `error.trace_id` | string или null | Идентификатор ошибки для поиска в логах |

Типовые error codes:

| HTTP-код | `error.code` | Назначение |
|---|---|---|
| `400` | `validation_error` | Общая ошибка валидации |
| `400` | `invalid` | Некорректное значение поля или query-параметра |
| `400` | `unique` | Нарушение уникальности данных |
| `401` | `not_authenticated` | Access token не передан |
| `401` | `authentication_failed` | Access token некорректен |
| `403` | `permission_denied` | Недостаточно прав |
| `404` | `not_found` | Объект не найден |
| `405` | `method_not_allowed` | HTTP-метод не разрешён |
| `409` | `conflict` | Конфликт состояния данных |
| `409` | `category_has_children` | Категория имеет дочерние категории |
| `409` | `category_has_transactions` | Категория используется в операциях |
| `409` | `category_has_budgets` | Категория используется в бюджетах |
| `409` | `integrity_error` | Нарушено ограничение целостности данных |
| `500` | `server_error` | Внутренняя ошибка сервера |

Пример ошибки авторизации:

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

Пример ошибки валидации query-параметра:

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

Пример ошибки конфликта:

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

Пример внутренней ошибки сервера:

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

Для ошибок `500` backend генерирует `trace_id` и пишет stack trace в логи.

## Логирование ошибок

Клиентские ошибки `4xx` логируются на уровне `WARNING`.

В лог попадают:

- `status_code`;
- `code`;
- `message`;
- `trace_id`;
- HTTP method;
- path;
- query params;
- user id;
- client ip.

Пример лога:

```text
API client error. status_code=400 code=invalid message=Некорректные данные запроса. trace_id=None method=GET path=/api/v1/users/ query_params={'is_staff': 'wrong'} user_id=72 client_ip=127.0.0.1
```

Серверные ошибки `5xx` логируются на уровне `ERROR` со stack trace.

## Пагинация

Для списков используется стандартная пагинация.

Параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы, максимум 100 |

Базовый размер страницы:

```text
20
```

Формат пагинированного ответа:

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

| API resource | ORM model | Статус | Назначение |
|---|---|---|---|
| `/api/v1/users/me/` | `User` | Реализовано | Данные текущего пользователя |
| `/api/v1/users/` | `User` | Реализовано | Администрирование пользователей |
| `/api/v1/finance/accounts/` | `Account` | Планируется | Счета пользователя |
| `/api/v1/finance/categories/` | `Category` | Реализовано | Категории доходов и расходов |
| `/api/v1/finance/categories/tree/` | `Category` | Реализовано | Дерево категорий |
| `/api/v1/finance/transactions/` | `Transaction` | Реализовано | Финансовые операции |
| `/api/v1/finance/budgets/` | `Budget` | Планируется | Бюджеты по категориям и периодам |
| `/api/v1/finance/goals/` | `Goal` | Планируется | Финансовые цели |
| `/api/v1/finance/reports/summary/` | `Transaction`, `Account`, `Category` | Планируется | Расчётная финансовая сводка |

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
| `datetime` | `DateTimeField` | `"2026-05-07T10:30:00+0300"` |

Денежные значения передаются строкой, чтобы избежать ошибок округления на стороне клиента.

## Служебные endpoints

### Health-check

| Поле | Значение |
|---|---|
| URL | `/health/` |
| Метод | `GET` |
| Доступ | Публичный |
| Статус | Реализовано |

Назначение: проверка состояния backend-сервиса.

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
  "timestamp": "2026-05-09T23:40:27.988851Z"
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

## Механизм аутентификации

В проекте используется JWT-аутентификация на базе Simple JWT.

Backend возвращает `access` и `refresh` tokens в JSON-ответе. На текущем этапе токены не устанавливаются в cookie. Frontend должен самостоятельно сохранить полученные tokens и передавать access token в защищённые запросы через HTTP-заголовок:

```http
Authorization: Bearer <access_token>
```

### Срок жизни токенов

| Token | Lifetime | Назначение |
|---|---|---|
| `access` | 15 минут | Используется для доступа к защищённым endpoints |
| `refresh` | 7 дней | Используется для получения нового access token |

### Обновление refresh token

Для refresh token включены:

| Настройка | Значение | Назначение |
|---|---|---|
| `ROTATE_REFRESH_TOKENS` | `true` | При обновлении выдаётся новый refresh token |
| `BLACKLIST_AFTER_ROTATION` | `true` | Старый refresh token добавляется в blacklist |
| `UPDATE_LAST_LOGIN` | `true` | При успешном входе обновляется `last_login` пользователя |

### Security notes

На текущем этапе используется схема token return в JSON-ответе. Это проще для разработки REST API и Postman-тестирования.

Для production-окружения можно рассмотреть хранение refresh token в `HttpOnly Secure SameSite` cookie, но это потребует отдельной настройки CSRF, CORS и frontend-логики.

### Ошибки авторизации

Все ошибки авторизации возвращаются в едином формате API:

```json
{
  "success": false,
  "error": {
    "status_code": 401,
    "code": "authentication_failed",
    "message": "Пользователь не авторизован.",
    "field_errors": null,
    "detail": "Неверные учётные данные.",
    "trace_id": null
  }
}
```

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
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new_access"
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
| Статус | Реализовано |

Назначение: получение данных текущего пользователя.

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
  "username": "demo",
  "email": "demo@example.com",
  "first_name": "Timofey",
  "last_name": "Demo",
  "role": "user",
  "is_active": true,
  "date_joined": "2026-05-07T23:51:53+0300"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Данные пользователя получены |
| `401` | Пользователь не авторизован |

---

### Обновление текущего пользователя

| Поле | Значение |
|---|---|
| URL | `/api/v1/users/me/` |
| Метод | `PATCH` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

Назначение: частичное обновление данных текущего пользователя.

Доступные поля:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `first_name` | string | Нет | Имя |
| `last_name` | string | Нет | Фамилия |

Пример запроса:

```http
PATCH /api/v1/users/me/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "first_name": "Timofey",
  "last_name": "Demo"
}
```

Пример успешного ответа:

```json
{
  "id": 1,
  "username": "demo",
  "email": "demo@example.com",
  "first_name": "Timofey",
  "last_name": "Demo",
  "role": "user",
  "is_active": true,
  "date_joined": "2026-05-07T23:51:53+0300"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Данные пользователя обновлены |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |

---

### Список пользователей

| Поле | Значение |
|---|---|
| URL | `/api/v1/users/` |
| Метод | `GET` |
| Доступ | Администратор |
| Статус | Реализовано |

Назначение: получение списка пользователей.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `is_active` | boolean | Нет | Фильтр по активности |
| `is_staff` | boolean | Нет | Фильтр по staff-статусу |
| `is_superuser` | boolean | Нет | Фильтр по superuser-статусу |
| `search` | string | Нет | Поиск по username или email |
| `ordering` | string | Нет | Сортировка |

Допустимые значения `ordering`:

```text
id
-id
username
-username
email
-email
date_joined
-date_joined
```

Пример запроса:

```http
GET /api/v1/users/?is_active=true&ordering=id HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <admin_access_token>
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
      "username": "demo",
      "email": "demo@example.com",
      "first_name": "",
      "last_name": "",
      "role": "user",
      "is_active": true,
      "is_staff": false,
      "is_superuser": false,
      "date_joined": "2026-05-07T23:51:53+0300",
      "last_login": null
    }
  ]
}
```

Пример ошибки query-параметра:

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

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список пользователей получен |
| `400` | Некорректные query-параметры |
| `401` | Пользователь не авторизован |
| `403` | Недостаточно прав |

---

### Создание пользователя администратором

| Поле | Значение |
|---|---|
| URL | `/api/v1/users/` |
| Метод | `POST` |
| Доступ | Администратор |
| Статус | Реализовано |

Назначение: создание пользователя администратором.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `username` | string | Да | Имя пользователя |
| `email` | string | Да | Email |
| `password` | string | Нет | Пароль, минимум 8 символов |
| `first_name` | string | Нет | Имя |
| `last_name` | string | Нет | Фамилия |
| `is_active` | boolean | Нет | Активность пользователя |
| `is_staff` | boolean | Нет | Staff-статус |
| `is_superuser` | boolean | Нет | Superuser-статус |

Пример запроса:

```http
POST /api/v1/users/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

```json
{
  "username": "created_user",
  "email": "created_user@example.com",
  "password": "created-password-123",
  "first_name": "Created",
  "last_name": "User",
  "is_active": true,
  "is_staff": false,
  "is_superuser": false
}
```

Пример успешного ответа:

```json
{
  "id": 3,
  "username": "created_user",
  "email": "created_user@example.com",
  "first_name": "Created",
  "last_name": "User",
  "role": "user",
  "is_active": true,
  "is_staff": false,
  "is_superuser": false,
  "date_joined": "2026-05-10T02:00:00+0300",
  "last_login": null
}
```

Пример ошибки уникальности:

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

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Пользователь создан |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `403` | Недостаточно прав |

---

### Получение, обновление и деактивация пользователя

| Поле | Значение |
|---|---|
| URL | `/api/v1/users/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Администратор |
| Статус | Реализовано |

Назначение: работа с конкретным пользователем.

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID пользователя |

`DELETE` не удаляет пользователя физически, а устанавливает:

```json
{
  "is_active": false
}
```

Администратор не может деактивировать сам себя через этот endpoint.

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Пользователь получен или обновлён |
| `204` | Пользователь деактивирован |
| `400` | Ошибка валидации или попытка деактивировать себя |
| `401` | Пользователь не авторизован |
| `403` | Недостаточно прав |
| `404` | Пользователь не найден |

## Finance endpoints

## Account endpoints

Endpoints счетов планируются к реализации.

### Список счетов

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка счетов текущего пользователя.

---

### Создание счёта

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание нового счёта пользователя.

---

### Получение, обновление и удаление счёта

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/accounts/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Если у счёта есть связанные операции, физическое удаление должно быть запрещено. В таком случае frontend может использовать частичное обновление и передать `is_active=false`, чтобы скрыть счёт без потери истории операций.

## Category endpoints

### Список категорий

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

Назначение: получение списка категорий доходов и расходов.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `type` | string | Нет | Тип категории: `income` или `expense` |
| `parent` | integer | Нет | ID родительской категории |
| `is_active` | boolean | Нет | Фильтр по активности категории |
| `ordering` | string | Нет | Сортировка |

Допустимые значения `ordering`:

```text
name
-name
type
-type
created_at
-created_at
```

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
      "id": 3,
      "parent": null,
      "name": "Продукты",
      "type": "expense",
      "is_active": true,
      "children_count": 1,
      "created_at": "2026-05-07T23:51:53+0300",
      "updated_at": "2026-05-08T01:11:32+0300"
    }
  ]
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Список категорий получен |
| `400` | Некорректные query-параметры |
| `401` | Пользователь не авторизован |

---

### Дерево категорий

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/tree/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

Назначение: получение категорий в виде дерева.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `type` | string | Нет | Тип категории: `income` или `expense` |
| `is_active` | boolean | Нет | Фильтр по активности |

Пример запроса:

```http
GET /api/v1/finance/categories/tree/?type=expense HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
[
  {
    "id": 3,
    "parent": null,
    "name": "Продукты",
    "type": "expense",
    "is_active": true,
    "children": [
      {
        "id": 8,
        "parent": 3,
        "name": "Супермаркеты",
        "type": "expense",
        "is_active": true,
        "children": [],
        "created_at": "2026-05-08T01:11:32+0300",
        "updated_at": "2026-05-08T01:11:32+0300"
      }
    ],
    "created_at": "2026-05-07T23:51:53+0300",
    "updated_at": "2026-05-07T23:51:53+0300"
  }
]
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Дерево категорий получено |
| `400` | Некорректные query-параметры |
| `401` | Пользователь не авторизован |

---

### Создание категории

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/categories/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

Назначение: создание категории доходов или расходов.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `parent` | integer или null | Нет | ID родительской категории |
| `name` | string | Да | Название категории |
| `type` | string | Да | Тип категории: `income` или `expense` |
| `is_active` | boolean | Нет | Активность категории |

Пример запроса:

```http
POST /api/v1/finance/categories/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "parent": 3,
  "name": "Супермаркеты",
  "type": "expense",
  "is_active": true
}
```

Пример успешного ответа:

```json
{
  "id": 8,
  "parent": 3,
  "name": "Супермаркеты",
  "type": "expense",
  "is_active": true,
  "children_count": 0,
  "created_at": "2026-05-08T01:11:32+0300",
  "updated_at": "2026-05-08T01:11:32+0300"
}
```

Пример ошибки:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "invalid",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "parent": [
        "Родительская категория должна иметь тот же тип."
      ]
    },
    "detail": null,
    "trace_id": null
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
| Статус | Реализовано |

Назначение: работа с конкретной категорией пользователя.

Path-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `id` | integer | Да | ID категории |

Пример запроса:

```http
GET /api/v1/finance/categories/3/ HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer <access_token>
```

Пример успешного ответа:

```json
{
  "id": 3,
  "parent": null,
  "name": "Продукты",
  "type": "expense",
  "is_active": true,
  "children_count": 1,
  "created_at": "2026-05-07T23:51:53+0300",
  "updated_at": "2026-05-07T23:51:53+0300"
}
```

Удаление категории запрещено, если у неё есть дочерние категории, связанные операции или бюджеты. В таком случае нужно использовать `PATCH` и передать `is_active=false`.

Пример ошибки конфликта:

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

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Категория получена или обновлена |
| `204` | Категория удалена |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `404` | Категория не найдена |
| `409` | Категорию нельзя удалить из-за связанных данных |

## Transaction endpoints

### Список операций

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/transactions/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

Назначение: получение списка финансовых операций пользователя.

Query-параметры:

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `page` | integer | Нет | Номер страницы |
| `page_size` | integer | Нет | Размер страницы |
| `account` | integer | Нет | Фильтр по счёту |
| `category` | integer | Нет | Фильтр по категории |
| `type` | string | Нет | Тип операции: `income` или `expense` |
| `date_from` | date | Нет | Начало периода |
| `date_to` | date | Нет | Конец периода |
| `ordering` | string | Нет | Сортировка |

Допустимые значения `ordering`:

```text
operation_date
-operation_date
amount
-amount
created_at
-created_at
```

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
      "category": 3,
      "type": "expense",
      "amount": "3200.00",
      "description": "Покупка продуктов",
      "operation_date": "2026-05-07",
      "created_at": "2026-05-07T23:51:53+0300",
      "updated_at": "2026-05-07T23:51:53+0300"
    }
  ]
}
```

Пример ошибки query-параметра:

```json
{
  "success": false,
  "error": {
    "status_code": 400,
    "code": "invalid",
    "message": "Некорректные данные запроса.",
    "field_errors": {
      "account": "Параметр должен быть целым числом."
    },
    "detail": null,
    "trace_id": null
  }
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
| Статус | Реализовано |

Назначение: создание новой финансовой операции.

Тело запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `account` | integer | Да | ID счёта пользователя |
| `category` | integer | Да | ID категории пользователя |
| `type` | string | Да | Тип операции: `income` или `expense` |
| `amount` | decimal | Да | Сумма операции |
| `description` | string | Нет | Описание операции |
| `operation_date` | date | Да | Дата операции |

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
  "category": 3,
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
  "category": 3,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+0300",
  "updated_at": "2026-05-07T10:30:00+0300"
}
```

Пример ошибки несовпадения типа операции и категории:

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

Возможные коды ответа:

| Код | Описание |
|---|---|
| `201` | Операция создана |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `404` | Связанный объект не найден |

---

### Получение, обновление и удаление операции

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/transactions/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Реализовано |

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
  "category": 3,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+0300",
  "updated_at": "2026-05-07T10:30:00+0300"
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
  "category": 3,
  "type": "expense",
  "amount": "1200.00",
  "description": "Покупка продуктов и бытовых товаров",
  "operation_date": "2026-05-07",
  "created_at": "2026-05-07T10:30:00+0300",
  "updated_at": "2026-05-07T10:35:00+0300"
}
```

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Операция получена или обновлена |
| `204` | Операция удалена |
| `400` | Ошибка валидации |
| `401` | Пользователь не авторизован |
| `404` | Операция не найдена |

## Budget endpoints

Endpoints бюджетов планируются к реализации.

### Список бюджетов

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка бюджетов текущего пользователя.

### Создание бюджета

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание бюджета по категории расходов за период.

### Получение, обновление и удаление бюджета

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/budgets/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

## Goal endpoints

Endpoints финансовых целей планируются к реализации.

### Список финансовых целей

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/` |
| Метод | `GET` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: получение списка финансовых целей текущего пользователя.

### Создание финансовой цели

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/` |
| Метод | `POST` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

Назначение: создание финансовой цели пользователя.

### Получение, обновление и удаление финансовой цели

| Поле | Значение |
|---|---|
| URL | `/api/v1/finance/goals/{id}/` |
| Методы | `GET`, `PATCH`, `DELETE` |
| Доступ | Авторизованный пользователь |
| Статус | Планируется |

## Reports endpoints

Endpoints отчётов планируются к реализации.

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
| `date_from` | date | Нет | Начало периода |
| `date_to` | date | Нет | Конец периода |
| `account` | integer | Нет | Фильтр по счёту |

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

Возможные коды ответа:

| Код | Описание |
|---|---|
| `200` | Отчёт сформирован |
| `400` | Некорректные параметры периода |
| `401` | Пользователь не авторизован |
# API Resources and URL Structure

Документ описывает структуру REST API для основного функционала backend-части BudgetWise.

Цель документа - зафиксировать основные ресурсы, URL, HTTP-методы, правила доступа и структуру будущих CRUD endpoints перед началом реализации.

## Общий принцип

Backend использует REST API на Django REST Framework.

Базовый префикс API:

```text
/api/v1/
```

Основные группы ресурсов:

```text
/api/v1/auth/
/api/v1/users/
/api/v1/finance/
```

Служебные endpoints:

```text
/health/
/api/schema/
/api/docs/
```

## Правила доступа

Большинство endpoints требуют JWT-аутентификацию.

Для защищённых запросов используется HTTP-заголовок:

```http
Authorization: Bearer <access_token>
```

Публичные endpoints:

| URL | Назначение |
|---|---|
| `/health/` | Проверка состояния backend-сервиса |
| `/api/v1/` | Корневой endpoint API |
| `/api/v1/auth/register/` | Регистрация пользователя |
| `/api/v1/auth/token/` | Получение JWT-токенов |
| `/api/v1/auth/token/refresh/` | Обновление JWT-токена |
| `/api/v1/auth/token/verify/` | Проверка JWT-токена |

Защищённые endpoints:

| URL | Назначение |
|---|---|
| `/api/v1/users/me/` | Данные текущего пользователя |
| `/api/v1/users/` | Управление пользователями, только для администратора |
| `/api/v1/finance/accounts/` | Счета пользователя |
| `/api/v1/finance/categories/` | Категории пользователя |
| `/api/v1/finance/transactions/` | Финансовые операции пользователя |
| `/api/v1/finance/budgets/` | Бюджеты пользователя |
| `/api/v1/finance/goals/` | Финансовые цели пользователя |
| `/api/v1/finance/reports/summary/` | Финансовая сводка |

Главное правило доступа к финансовым данным:

```text
Пользователь может работать только со своими финансовыми данными.
```

Это правило должно соблюдаться на уровне queryset, serializers, services и permission-проверок.

## Auth resources

### Register

| Метод | URL | Назначение | Доступ |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | Регистрация пользователя | Публичный |

Создаёт нового пользователя.

Основные поля запроса:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `username` | string | Да | Имя пользователя |
| `email` | string | Да | Email пользователя |
| `password` | string | Да | Пароль |
| `password_confirm` | string | Да | Подтверждение пароля |

Основные поля ответа:

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID пользователя |
| `username` | string | Имя пользователя |
| `email` | string | Email пользователя |

### Token

| Метод | URL | Назначение | Доступ |
|---|---|---|---|
| `POST` | `/api/v1/auth/token/` | Получение access и refresh token | Публичный |
| `POST` | `/api/v1/auth/token/refresh/` | Обновление access token | Публичный |
| `POST` | `/api/v1/auth/token/verify/` | Проверка token | Публичный |

Токены используются для доступа к защищённым endpoints.

## Users resources

### Current user

| Метод | URL | Назначение | Доступ |
|---|---|---|---|
| `GET` | `/api/v1/users/me/` | Получить текущего пользователя | Авторизованный пользователь |
| `PATCH` | `/api/v1/users/me/` | Частично обновить текущего пользователя | Авторизованный пользователь |

Основные поля ответа:

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID пользователя |
| `username` | string | Имя пользователя |
| `email` | string | Email пользователя |
| `first_name` | string | Имя |
| `last_name` | string | Фамилия |
| `is_active` | boolean | Активность пользователя |
| `date_joined` | datetime | Дата регистрации |

### Users management

Endpoints управления пользователями нужны для административных сценариев.

| Метод | URL | Назначение | Доступ |
|---|---|---|---|
| `GET` | `/api/v1/users/` | Получить список пользователей | Администратор |
| `POST` | `/api/v1/users/` | Создать пользователя | Администратор |
| `GET` | `/api/v1/users/{id}/` | Получить пользователя | Администратор |
| `PATCH` | `/api/v1/users/{id}/` | Обновить пользователя | Администратор |
| `DELETE` | `/api/v1/users/{id}/` | Деактивировать или удалить пользователя | Администратор |

На этапе MVP предпочтительно не удалять пользователя физически, а использовать `is_active=false`.

## Roles

В рамках MVP роли можно реализовать на базе стандартных полей Django:

| Роль | Условие |
|---|---|
| `user` | Обычный авторизованный пользователь |
| `admin` | Пользователь с `is_staff=True` или `is_superuser=True` |

Отдельная таблица ролей на этапе MVP не создаётся. При необходимости в будущем можно использовать Django Groups или отдельную модель ролей.

## Finance resources

Финансовые ресурсы доступны только авторизованному пользователю.

К финансовым ресурсам относятся:

```text
accounts
categories
transactions
budgets
goals
reports
```

Каждый объект финансового модуля должен быть связан с владельцем через пользователя напрямую или через связанные сущности.

## Accounts

Ресурс:

```text
/api/v1/finance/accounts/
```

Назначение: управление виртуальными счетами пользователя.

Это не реальные банковские счета. Счёт используется внутри приложения для учёта денег, например карта, наличные, накопительный счёт.

### Методы

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/accounts/` | Список счетов |
| `POST` | `/api/v1/finance/accounts/` | Создать счёт |
| `GET` | `/api/v1/finance/accounts/{id}/` | Получить счёт |
| `PATCH` | `/api/v1/finance/accounts/{id}/` | Частично обновить счёт |
| `DELETE` | `/api/v1/finance/accounts/{id}/` | Удалить или отключить счёт |

### Основные поля

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID счёта |
| `name` | string | Название счёта |
| `balance` | decimal | Баланс |
| `currency` | string | Валюта |
| `is_active` | boolean | Активность |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата обновления |

### Query-параметры

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `is_active` | boolean | Фильтр по активности счёта |
| `ordering` | string | Сортировка |

### Правила

- пользователь видит только свои счета;
- название счёта должно быть уникальным в рамках пользователя;
- валюта хранится трёхбуквенным кодом, например `RUB`;
- баланс хранится как decimal;
- если у счёта есть связанные операции, физическое удаление должно быть запрещено;
- для скрытия счёта используется `PATCH` с `is_active=false`.

## Categories

Ресурс:

```text
/api/v1/finance/categories/
```

Назначение: управление категориями доходов и расходов.

В новом эпике категории должны поддерживать иерархию. Для этого в ORM-модель `Category` нужно добавить поле `parent`.

### Планируемая структура категории

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID категории |
| `parent` | integer или null | Родительская категория |
| `name` | string | Название категории |
| `type` | string | `income` или `expense` |
| `is_active` | boolean | Активность |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата обновления |

### Методы

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/categories/` | Список категорий |
| `POST` | `/api/v1/finance/categories/` | Создать категорию |
| `GET` | `/api/v1/finance/categories/{id}/` | Получить категорию |
| `PATCH` | `/api/v1/finance/categories/{id}/` | Частично обновить категорию |
| `DELETE` | `/api/v1/finance/categories/{id}/` | Удалить или отключить категорию |

### Дополнительный endpoint для дерева категорий

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/categories/tree/` | Получить категории в виде дерева |

### Query-параметры

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `type` | string | `income` или `expense` |
| `parent` | integer | Фильтр по родительской категории |
| `is_active` | boolean | Фильтр по активности |
| `ordering` | string | Сортировка |

### Правила иерархии

- категория может не иметь родителя;
- родительская категория должна принадлежать тому же пользователю;
- родительская категория должна иметь тот же `type`;
- категория не может быть родителем самой себе;
- циклические связи запрещены;
- если категория используется в операциях или бюджетах, физическое удаление должно быть запрещено;
- для скрытия категории используется `PATCH` с `is_active=false`.

## Transactions

Ресурс:

```text
/api/v1/finance/transactions/
```

Назначение: управление финансовыми операциями пользователя.

Операция может быть доходом или расходом.

### Методы

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/transactions/` | Список операций |
| `POST` | `/api/v1/finance/transactions/` | Создать операцию |
| `GET` | `/api/v1/finance/transactions/{id}/` | Получить операцию |
| `PATCH` | `/api/v1/finance/transactions/{id}/` | Частично обновить операцию |
| `DELETE` | `/api/v1/finance/transactions/{id}/` | Удалить операцию |

### Основные поля

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID операции |
| `account` | integer | ID счёта |
| `category` | integer | ID категории |
| `type` | string | `income` или `expense` |
| `amount` | decimal | Сумма операции |
| `description` | string | Описание |
| `operation_date` | date | Дата операции |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата обновления |

### Query-параметры

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `account` | integer | Фильтр по счёту |
| `category` | integer | Фильтр по категории |
| `type` | string | `income` или `expense` |
| `date_from` | date | Начало периода |
| `date_to` | date | Конец периода |
| `ordering` | string | Сортировка, например `operation_date` или `-operation_date` |

### Правила

- пользователь видит только свои операции;
- сумма операции должна быть больше нуля;
- счёт должен принадлежать текущему пользователю;
- категория должна принадлежать текущему пользователю;
- тип категории должен совпадать с типом операции;
- дата операции обязательна;
- денежные значения передаются строкой, например `"1200.00"`.

## Budgets

Ресурс:

```text
/api/v1/finance/budgets/
```

Назначение: управление бюджетами по категориям расходов.

### Методы

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/budgets/` | Список бюджетов |
| `POST` | `/api/v1/finance/budgets/` | Создать бюджет |
| `GET` | `/api/v1/finance/budgets/{id}/` | Получить бюджет |
| `PATCH` | `/api/v1/finance/budgets/{id}/` | Частично обновить бюджет |
| `DELETE` | `/api/v1/finance/budgets/{id}/` | Удалить бюджет |

### Основные поля

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID бюджета |
| `category` | integer | ID категории |
| `amount_limit` | decimal | Лимит бюджета |
| `period_start` | date | Начало периода |
| `period_end` | date | Конец периода |
| `is_active` | boolean | Активность |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата обновления |

### Query-параметры

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `category` | integer | Фильтр по категории |
| `is_active` | boolean | Фильтр по активности |
| `period_start` | date | Начало периода |
| `period_end` | date | Конец периода |
| `ordering` | string | Сортировка |

### Правила

- пользователь видит только свои бюджеты;
- лимит должен быть больше нуля;
- дата окончания периода не может быть раньше даты начала;
- категория должна принадлежать текущему пользователю;
- бюджет создаётся для категории расходов;
- для одной категории и одинакового периода не должно быть дублей.

## Goals

Ресурс:

```text
/api/v1/finance/goals/
```

Назначение: управление финансовыми целями пользователя.

### Методы

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/goals/` | Список целей |
| `POST` | `/api/v1/finance/goals/` | Создать цель |
| `GET` | `/api/v1/finance/goals/{id}/` | Получить цель |
| `PATCH` | `/api/v1/finance/goals/{id}/` | Частично обновить цель |
| `DELETE` | `/api/v1/finance/goals/{id}/` | Удалить цель |

### Основные поля

| Поле | Тип | Описание |
|---|---|---|
| `id` | integer | ID цели |
| `account` | integer или null | Связанный счёт |
| `name` | string | Название цели |
| `target_amount` | decimal | Целевая сумма |
| `current_amount` | decimal | Текущая сумма |
| `deadline` | date или null | Срок достижения |
| `status` | string | `active`, `completed`, `cancelled` |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата обновления |

### Query-параметры

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `status` | string | Статус цели |
| `account` | integer | Фильтр по связанному счёту |
| `ordering` | string | Сортировка |

### Правила

- пользователь видит только свои цели;
- целевая сумма должна быть больше нуля;
- текущая сумма не может быть отрицательной;
- связанный счёт должен принадлежать текущему пользователю;
- название цели должно быть уникальным в рамках пользователя.

## Reports

Ресурс:

```text
/api/v1/finance/reports/
```

На этапе MVP отчёты не являются отдельной таблицей. Они формируются на основе операций, счетов и категорий.

### Summary report

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v1/finance/reports/summary/` | Краткая финансовая сводка |

Основные параметры:

| Параметр | Тип | Описание |
|---|---|---|
| `date_from` | date | Начало периода |
| `date_to` | date | Конец периода |
| `account` | integer | Фильтр по счёту |

Основные поля ответа:

| Поле | Тип | Описание |
|---|---|---|
| `income_total` | decimal | Общая сумма доходов |
| `expense_total` | decimal | Общая сумма расходов |
| `balance_delta` | decimal | Разница между доходами и расходами |
| `period` | object | Период отчёта |

## Общие query-параметры списков

| Параметр | Тип | Описание |
|---|---|---|
| `page` | integer | Номер страницы |
| `page_size` | integer | Размер страницы |
| `ordering` | string | Сортировка |

Базовый размер страницы:

```text
20
```

Максимальный размер страницы:

```text
100
```

## Единый формат ошибок

API использует единый формат ошибок:

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

Этот формат применяется для ошибок валидации, ошибок доступа и других ошибок API.

## HTTP-коды

| Код | Значение |
|---|---|
| `200 OK` | Успешное получение или обновление объекта |
| `201 Created` | Объект создан |
| `204 No Content` | Объект удалён |
| `400 Bad Request` | Ошибка валидации |
| `401 Unauthorized` | Пользователь не авторизован |
| `403 Forbidden` | Недостаточно прав |
| `404 Not Found` | Объект не найден |
| `409 Conflict` | Объект нельзя удалить или изменить из-за связанных данных |
| `500 Internal Server Error` | Внутренняя ошибка сервера |

## DRF router plan

Для CRUD-ресурсов планируется использовать DRF router и ViewSet.

Планируемые ViewSet:

| ViewSet | URL |
|---|---|
| `AccountViewSet` | `/api/v1/finance/accounts/` |
| `CategoryViewSet` | `/api/v1/finance/categories/` |
| `TransactionViewSet` | `/api/v1/finance/transactions/` |
| `BudgetViewSet` | `/api/v1/finance/budgets/` |
| `GoalViewSet` | `/api/v1/finance/goals/` |

Для пользователей:

| View | URL |
|---|---|
| `CurrentUserView` | `/api/v1/users/me/` |
| `UserViewSet` | `/api/v1/users/` |

Для регистрации и токенов:

| View | URL |
|---|---|
| `RegisterView` | `/api/v1/auth/register/` |
| `TokenObtainPairView` | `/api/v1/auth/token/` |
| `TokenRefreshView` | `/api/v1/auth/token/refresh/` |
| `TokenVerifyView` | `/api/v1/auth/token/verify/` |

## Итоговая структура URL

```text
/health/
/api/schema/
/api/docs/

/api/v1/

/api/v1/auth/register/
/api/v1/auth/token/
/api/v1/auth/token/refresh/
/api/v1/auth/token/verify/

/api/v1/users/
/api/v1/users/{id}/
/api/v1/users/me/

/api/v1/finance/accounts/
/api/v1/finance/accounts/{id}/

/api/v1/finance/categories/
/api/v1/finance/categories/{id}/
/api/v1/finance/categories/tree/

/api/v1/finance/transactions/
/api/v1/finance/transactions/{id}/

/api/v1/finance/budgets/
/api/v1/finance/budgets/{id}/

/api/v1/finance/goals/
/api/v1/finance/goals/{id}/

/api/v1/finance/reports/summary/
```

## Следующие шаги реализации

После утверждения структуры ресурсов реализация должна идти в таком порядке:

1. Подготовить базовые serializers, permissions и ViewSet-структуру.
2. Реализовать CRUD для счетов, так как операции зависят от счетов.
3. Реализовать CRUD для категорий, включая иерархию.
4. Реализовать CRUD для операций.
5. Реализовать endpoints пользователя и административное управление пользователями.
6. Проверить валидацию, ограничения доступа и единый формат ошибок.
7. Покрыть CRUD endpoints базовыми автотестами.
8. Обновить OpenAPI/Swagger-документацию.
# Postman Collection

В папке хранятся файлы для ручного тестирования API через Postman.

## Файлы

| Файл | Назначение |
|---|---|
| `BudgetWiseBackend.postman_collection.json` | Коллекция запросов Postman |
| `BudgetWiseBackend.local.postman_environment.json` | Локальное окружение с переменными |

## Импорт в Postman

1. Открыть Postman.
2. Нажать `Import`.
3. Выбрать файлы:
   - `docs/postman/BudgetWiseBackend.postman_collection.json`;
   - `docs/postman/BudgetWiseBackend.local.postman_environment.json`.
4. Выбрать окружение `BudgetWiseBackend Local` в правом верхнем углу Postman.
5. Проверить переменную `base_url`.

Для локального запуска значение должно быть:

```text
http://127.0.0.1:8000
```

## Запуск backend

Backend можно запустить локально:

```bash
python manage.py runserver
```

Или через Docker Compose:

```bash
docker compose up -d
```

Проверить, что контейнеры запущены:

```bash
docker compose ps
```

## Подготовка demo-данных

Перед тестированием защищённых endpoints нужно создать demo-пользователя и demo-данные.

Локально:

```bash
python manage.py seed_demo_data
```

Через Docker Compose:

```bash
docker compose exec backend python manage.py seed_demo_data
```

Команда создаёт:

- demo-пользователя;
- счета;
- категории;
- операции;
- бюджет;
- финансовую цель.

По умолчанию используются данные:

```text
username: demo
password: demo-password-123
email: demo@example.com
```

## Получение access token

Пока auth endpoints не реализованы, access token можно получить через Django shell.

Локально:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from rest_framework_simplejwt.tokens import RefreshToken; User = get_user_model(); user = User.objects.get(username='demo'); token = RefreshToken.for_user(user); print(str(token.access_token))"
```

Через Docker Compose:

```bash
docker compose exec backend python manage.py shell -c "from django.contrib.auth import get_user_model; from rest_framework_simplejwt.tokens import RefreshToken; User = get_user_model(); user = User.objects.get(username='demo'); token = RefreshToken.for_user(user); print(str(token.access_token))"
```

Полученный токен нужно вставить в переменную окружения Postman:

```text
access_token
```

После реализации auth endpoints запрос `Get token - planned` можно будет использовать для автоматического получения и сохранения токенов.

## Рекомендуемый порядок проверки

1. `00 Health / Health check`
2. `00 Health / API root`
3. `02 Finance - Categories / List categories`
4. `02 Finance - Categories / Create category`
5. `02 Finance - Categories / Create child category`
6. `02 Finance - Categories / Categories tree`
7. `03 Finance - Transactions / List transactions`
8. `03 Finance - Transactions / Create transaction`
9. `03 Finance - Transactions / Get transaction`
10. `03 Finance - Transactions / Update transaction`
11. `03 Finance - Transactions / Delete transaction`

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `base_url` | Базовый адрес backend API |
| `username` | Имя demo-пользователя |
| `password` | Пароль demo-пользователя |
| `access_token` | JWT access token |
| `refresh_token` | JWT refresh token |
| `account_id` | ID счёта для создания операций |
| `income_category_id` | ID категории доходов |
| `expense_category_id` | ID категории расходов |
| `category_id` | ID категории, созданной через Postman |
| `child_category_id` | ID дочерней категории |
| `transaction_id` | ID операции, созданной через Postman |

## Проверка health-check

Запрос:

```text
GET {{base_url}}/health/
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "service": "BudgetWiseBackend",
  "version": "1.0.0",
  "timestamp": "2026-05-08T00:00:00+00:00"
}
```

## Проверка API root

Запрос:

```text
GET {{base_url}}/api/v1/
```

Ожидаемый ответ содержит:

```json
{
  "service": "BudgetWiseBackend API",
  "version": "v1"
}
```

## Проверка категорий

Для проверки категорий используется группа:

```text
02 Finance - Categories
```

Основные запросы:

| Запрос | Назначение |
|---|---|
| `List categories` | Получить список категорий |
| `List expense categories` | Получить активные категории расходов |
| `Categories tree` | Получить категории в виде дерева |
| `Create category` | Создать корневую категорию |
| `Create child category` | Создать дочернюю категорию |
| `Get category` | Получить категорию по ID |
| `Update category` | Обновить категорию |
| `Delete child category` | Удалить или деактивировать дочернюю категорию |

После выполнения `Create category` Postman сохраняет ID созданной категории в переменную:

```text
category_id
```

После выполнения `Create child category` Postman сохраняет ID дочерней категории в переменную:

```text
child_category_id
```

## Проверка операций

Для проверки операций используется группа:

```text
03 Finance - Transactions
```

Основные запросы:

| Запрос | Назначение |
|---|---|
| `List transactions` | Получить список операций |
| `List expense transactions` | Получить операции расходов |
| `Create transaction` | Создать операцию |
| `Get transaction` | Получить операцию по ID |
| `Update transaction` | Обновить операцию |
| `Delete transaction` | Удалить операцию |

Для создания операции используются переменные:

```text
account_id
expense_category_id
```

После выполнения `Create transaction` Postman сохраняет ID созданной операции в переменную:

```text
transaction_id
```

## OpenAPI и Swagger

В группе `99 Docs` находятся запросы:

| Запрос | URL | Назначение |
|---|---|---|
| `OpenAPI schema` | `/api/schema/` | Получить OpenAPI-схему |
| `Swagger UI` | `/api/docs/` | Открыть Swagger-документацию |

## Важное правило

Токены и реальные пароли не нужно коммитить в репозиторий.

Файл окружения содержит только локальные demo-значения. Значение `access_token` должно оставаться пустым в Git.

## Обновление коллекции

Если API меняется, коллекцию нужно обновлять.

Рекомендуемый порядок:

1. Изменить или добавить запросы в Postman.
2. Экспортировать коллекцию через `Export`.
3. Заменить файл:

```text
docs/postman/BudgetWiseBackend.postman_collection.json
```

4. Проверить diff в Git.
5. Закоммитить изменения.

Окружение обновлять только если добавились новые переменные.
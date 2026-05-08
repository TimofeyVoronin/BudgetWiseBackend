# OpenAPI Documentation

В папке хранится сгенерированная OpenAPI-схема backend API проекта BudgetWiseBackend.

## Файлы

| Файл | Назначение |
|---|---|
| `schema.yaml` | OpenAPI-схема, сгенерированная через `drf-spectacular` |
| `README.md` | Инструкция по генерации и проверке OpenAPI/Swagger-документации |

## Swagger UI

Swagger-документация доступна по адресу:

```text
http://127.0.0.1:8000/api/docs/
```

OpenAPI-схема доступна по адресу:

```text
http://127.0.0.1:8000/api/schema/
```

## Генерация схемы

Перед генерацией нужно убедиться, что зависимости установлены, миграции применены, а проект проходит проверку:

```bash
python manage.py check
```

Сгенерировать OpenAPI-схему локально:

```bash
python manage.py spectacular --file docs/openapi/schema.yaml --validate
```

Если проект запущен через Docker Compose:

```bash
docker compose exec backend python manage.py spectacular --file docs/openapi/schema.yaml --validate
```

Если в проект добавлены команды Makefile, можно использовать:

```bash
make schema
```

или для Docker Compose:

```bash
make schema-docker
```

## Проверка Swagger UI

Запустить backend локально:

```bash
python manage.py runserver
```

Или через Docker Compose:

```bash
docker compose up -d
```

После запуска открыть в браузере:

```text
http://127.0.0.1:8000/api/docs/
```

В Swagger UI должны отображаться основные endpoints:

```text
/api/v1/users/
/api/v1/users/{id}/
/api/v1/users/me/

/api/v1/finance/categories/
/api/v1/finance/categories/{id}/
/api/v1/finance/categories/tree/

/api/v1/finance/transactions/
/api/v1/finance/transactions/{id}/
```

## Проверка OpenAPI schema endpoint

Проверить доступность схемы можно через curl:

```bash
curl http://127.0.0.1:8000/api/schema/
```

Ожидаемый результат: ответ со схемой OpenAPI в формате YAML.

## Авторизация в Swagger UI

Защищённые endpoints требуют JWT access token.

Формат заголовка:

```text
Authorization: Bearer <access_token>
```

В Swagger UI нужно нажать кнопку `Authorize` и вставить значение в формате:

```text
Bearer <access_token>
```

Пока auth endpoints не реализованы полностью, access token можно получить через Django shell:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from rest_framework_simplejwt.tokens import RefreshToken; User = get_user_model(); user = User.objects.get(username='demo'); token = RefreshToken.for_user(user); print(str(token.access_token))"
```

Для Docker Compose:

```bash
docker compose exec backend python manage.py shell -c "from django.contrib.auth import get_user_model; from rest_framework_simplejwt.tokens import RefreshToken; User = get_user_model(); user = User.objects.get(username='demo'); token = RefreshToken.for_user(user); print(str(token.access_token))"
```

## Когда нужно обновлять схему

Файл `schema.yaml` нужно генерировать заново, если изменились:

- serializers;
- views;
- viewsets;
- urls;
- permissions;
- request/response fields;
- query parameters;
- HTTP-коды;
- описание endpoints.

После изменений нужно выполнить:

```bash
python manage.py spectacular --file docs/openapi/schema.yaml --validate
```

Затем проверить diff:

```bash
git diff docs/openapi/schema.yaml
```

## Возможные warnings

При генерации схемы `drf-spectacular` может вывести warnings.

Не все warnings являются критичными. Обычно нужно проверить предупреждения, если они связаны с:

- неизвестным serializer;
- нераспознанным типом поля;
- отсутствующим request body;
- некорректным response schema;
- endpoints, которые должны быть в документации, но не отображаются.

Если warning относится к текущим CRUD endpoints, его лучше исправить до коммита.

## Финальная проверка перед коммитом

```bash
python manage.py check
python manage.py test apps.finance apps.users
python manage.py spectacular --file docs/openapi/schema.yaml --validate
```
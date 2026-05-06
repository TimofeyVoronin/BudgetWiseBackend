# BudgetWiseBackend

Backend-часть прогрессивного веб-приложения для управления личными финансами.

Проект разрабатывается в рамках дипломной работы на тему:  
**«Прогрессивное веб-приложение для управления финансами. Серверная часть»**.

## Цель проекта

Цель проекта - разработать серверную часть веб-приложения, которое помогает пользователю учитывать личные финансы, управлять счетами, категориями, операциями, бюджетами и получать базовую финансовую аналитику через REST API.

Backend отвечает за хранение и обработку финансовых данных, авторизацию пользователей, проверку прав доступа, бизнес-логику финансовых операций и предоставление API для frontend-приложения.

## Целевая аудитория

Основная аудитория приложения:

- пользователи, которые хотят вести личный или семейный бюджет;
- пользователи, которым нужно видеть доходы, расходы и остатки по счетам;
- пользователи, которые хотят разделять операции по категориям;
- пользователи, которым важно получать отчеты и аналитику по финансовым данным.

Также проект ориентирован на frontend-разработчика, который использует backend API для реализации клиентской части приложения.

## Основные сценарии использования

Пользователь сможет:

- зарегистрироваться и авторизоваться в приложении;
- управлять личными счетами;
- создавать категории доходов и расходов;
- добавлять финансовые операции;
- просматривать историю операций;
- фильтровать и сортировать финансовые данные;
- получать базовые отчеты по доходам, расходам и балансу;
- работать с бюджетами и финансовыми целями.

## MVP

MVP проекта включает серверную часть со следующими возможностями:

1. **Пользователи и авторизация**
   - пользовательская модель на базе Django `AbstractUser`;
   - JWT-аутентификация;
   - получение данных текущего пользователя.

2. **Финансовые сущности**
   - счета пользователя;
   - категории доходов и расходов;
   - операции по счетам;
   - базовые ограничения доступа к данным пользователя.

3. **API**
   - REST API на Django REST Framework;
   - версионирование через префикс `/api/v1/`;
   - единый формат ошибок;
   - пагинация списков;
   - OpenAPI-документация.

4. **Инфраструктура разработки**
   - настройки окружений `base/dev/prod`;
   - подключение PostgreSQL через `.env`;
   - CORS для взаимодействия с frontend-приложением;
   - health-check endpoint `/health/`;
   - базовое логирование.

## Технологический стек

- Python 3.12
- Django 5.2
- Django REST Framework
- PostgreSQL
- Simple JWT
- drf-spectacular
- django-cors-headers
- django-environ
- Docker для локального запуска PostgreSQL

## Структура проекта

```text
BudgetWiseBackend/
├── apps/
│   ├── common/
│   │   ├── exceptions.py
│   │   ├── pagination.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── finance/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   └── users/
│       ├── admin.py
│       ├── models.py
│       ├── serializers.py
│       ├── urls.py
│       └── views.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── api_urls.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── logs/
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

## Быстрый старт

Раздел описывает запуск backend-части проекта в локальном dev-окружении через WSL.

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd BudgetWiseBackend
```

### 2. Создание виртуального окружения

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Создать файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Пример основных переменных:

```env
SECRET_KEY=django-insecure-budgetwise-dev-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=finance_db
POSTGRES_USER=finance_user
POSTGRES_PASSWORD=finance_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CORS_ALLOW_CREDENTIALS=False

DJANGO_LOG_LEVEL=INFO
DJANGO_SQL_LOG_LEVEL=WARNING
APP_LOG_LEVEL=DEBUG
```

Файл `.env` не должен попадать в Git.

### 5. Запуск PostgreSQL для разработки

Если PostgreSQL запускается через Docker-контейнер:

```bash
docker run --name budgetwise-postgres \
  -e POSTGRES_DB=finance_db \
  -e POSTGRES_USER=finance_user \
  -e POSTGRES_PASSWORD=finance_password \
  -p 5432:5432 \
  -d postgres:16
```

Если контейнер уже создан, но остановлен:

```bash
docker start budgetwise-postgres
```

Проверить, что контейнер запущен:

```bash
docker ps
```

### 6. Применение миграций

```bash
python manage.py migrate
```

### 7. Запуск backend-сервера

```bash
python manage.py runserver
```

После запуска доступны основные endpoints:

| URL | Назначение |
|---|---|
| `http://127.0.0.1:8000/health/` | Проверка состояния backend-сервиса |
| `http://127.0.0.1:8000/api/v1/` | Корневой endpoint API версии v1 |
| `http://127.0.0.1:8000/api/schema/` | OpenAPI-схема |
| `http://127.0.0.1:8000/api/docs/` | Swagger-документация API |

## Проверка проекта

Проверка конфигурации Django:

```bash
python manage.py check
```

Проверка применённых миграций:

```bash
python manage.py showmigrations
```

Проверка подключения к базе данных:

```bash
python manage.py shell -c "from django.db import connection; print(connection.vendor); print(connection.settings_dict['NAME']); print(connection.settings_dict['HOST']); print(connection.settings_dict['PORT'])"
```

Ожидаемый результат:

```text
postgresql
finance_db
localhost
5432
```

## Запуск тестов

На текущем этапе можно использовать стандартный запуск тестов Django:

```bash
python manage.py test
```

Тесты будут расширяться по мере реализации модулей `users` и `finance`.

## Проверка форматирования и качества кода

Линтеры и форматтеры будут подключены отдельным шагом. До их настройки минимальная обязательная проверка проекта:

```bash
python manage.py check
```

## Frontend

Frontend-часть разрабатывается отдельно в другом репозитории. Backend предоставляет REST API, к которому frontend обращается по HTTP.

Для локальной разработки CORS настроен для следующих адресов:

```text
http://localhost:5173
http://127.0.0.1:5173
```

## Структура API

Backend использует версионирование API через URL-префикс `/api/v1/`.

Основные маршруты:

| Метод | URL | Назначение |
|---|---|---|
| GET | `/health/` | Проверка состояния backend-сервиса |
| GET | `/api/v1/` | Корневой endpoint API версии v1 |
| Разные | `/api/v1/users/` | Маршруты пользователей, профиля и авторизации |
| Разные | `/api/v1/finance/` | Маршруты финансового модуля: счета, категории, операции |
| GET | `/api/schema/` | OpenAPI-схема |
| GET | `/api/docs/` | Swagger-документация API |

Текущая версия API: `v1`.

Версионирование выполнено через URL-префикс. Это позволяет в будущем добавить новую версию API, например `/api/v2/`, без нарушения совместимости с существующими клиентами.

## Текущий статус

На текущем этапе подготовлена инфраструктурная основа backend-проекта:

- создан Django-проект;
- подключен Django REST Framework;
- создана структура приложений `users`, `finance`, `common`;
- добавлена пользовательская модель;
- настройки разделены на `base`, `dev` и `prod`;
- подключен PostgreSQL через переменные окружения;
- настроены DRF, JWT, CORS, логирование и health-check;
- добавлена структура API с версионированием `/api/v1/`;
- первичные миграции применены в PostgreSQL.
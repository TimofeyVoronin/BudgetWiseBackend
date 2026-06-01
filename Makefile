.PHONY: help build up dev down restart logs logs-backend logs-db logs-redis logs-celery-worker logs-celery-beat ps migrate makemigrations shell test check seed createsuperuser celery-worker celery-beat celery-inspect clean

help:
	@echo "BudgetWiseBackend commands:"
	@echo ""
	@echo "  make build          Build Docker images"
	@echo "  make up             Start services in background"
	@echo "  make dev            Build and start services in foreground"
	@echo "  make down           Stop services"
	@echo "  make restart        Restart services"
	@echo "  make logs           Show logs for all services"
	@echo "  make logs-backend   Show backend logs"
	@echo "  make logs-db        Show database logs"
	@echo "  make logs-redis     Show Redis logs"
	@echo "  make logs-celery-worker Show Celery worker logs"
	@echo "  make logs-celery-beat Show Celery beat logs"
	@echo "  make ps             Show containers status"
	@echo "  make migrate        Run migrations inside backend container"
	@echo "  make makemigrations Create migrations inside backend container"
	@echo "  make shell          Open Django shell inside backend container"
	@echo "  make test           Run Django tests inside backend container"
	@echo "  make check          Run Django system check inside backend container"
	@echo "  make seed           Load demo finance data"
	@echo "  make createsuperuser Create Django superuser"
	@echo "  make clean          Stop services and remove volumes"

build:
	docker compose build

up:
	docker compose up -d

dev:
	docker compose up --build

down:
	docker compose down

restart:
	docker compose down
	docker compose up -d

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-db:
	docker compose logs -f db

logs-redis:
	docker compose logs -f redis

logs-celery-worker:
	docker compose logs -f celery_worker

logs-celery-beat:
	docker compose logs -f celery_beat

ps:
	docker compose ps

migrate:
	docker compose exec backend python manage.py migrate

makemigrations:
	docker compose exec backend python manage.py makemigrations

shell:
	docker compose exec backend python manage.py shell

test:
	docker compose exec backend python manage.py test

check:
	docker compose exec backend python manage.py check

celery-worker:
	docker compose exec celery_worker celery -A config inspect ping

celery-beat:
	docker compose logs -f celery_beat

celery-inspect:
	docker compose exec celery_worker celery -A config inspect registered

seed:
	docker compose exec backend python manage.py seed_demo_data

createsuperuser:
	docker compose exec backend python manage.py createsuperuser

clean:
	docker compose down -v
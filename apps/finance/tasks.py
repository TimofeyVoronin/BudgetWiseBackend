from __future__ import annotations

import logging
from datetime import date
from typing import Any

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.finance.currencies.rates import refresh_user_currency_rates
from apps.finance.models import UserCurrency
from apps.finance.planned_transactions.services import run_due_planned_transactions
from apps.finance.recurring_transactions.services import run_due_recurring_transactions


logger = logging.getLogger(__name__)


def _parse_task_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


@shared_task(
    bind=True,
    name="apps.finance.run_due_recurring_transactions",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_due_recurring_transactions_task(
    self,
    run_date: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed_date = _parse_task_date(run_date)
    summary = run_due_recurring_transactions(
        run_date=parsed_date,
        limit=limit,
        dry_run=dry_run,
    )
    result = summary.as_dict()
    logger.info(
        "Recurring transactions task finished. task_id=%s processed=%s created=%s failed=%s skipped=%s completed=%s",
        self.request.id,
        result["processed_count"],
        result["created_count"],
        result["failed_count"],
        result["skipped_count"],
        result["completed_count"],
    )
    return result


@shared_task(
    bind=True,
    name="apps.finance.convert_due_planned_transactions",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def convert_due_planned_transactions_task(
    self,
    run_date: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed_date = _parse_task_date(run_date)
    summary = run_due_planned_transactions(
        run_date=parsed_date,
        limit=limit,
        dry_run=dry_run,
    )
    result = summary.as_dict()
    logger.info(
        "Planned transactions task finished. task_id=%s processed=%s converted=%s failed=%s skipped=%s",
        self.request.id,
        result["processed_count"],
        result["converted_count"],
        result["failed_count"],
        result["skipped_count"],
    )
    return result


@shared_task(
    bind=True,
    name="apps.finance.refresh_currency_rates",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def refresh_currency_rates_task(
    self,
    user_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    user_ids = _get_currency_rate_user_ids(user_id=user_id)
    refreshed_ids: list[int] = []
    failed: list[dict[str, Any]] = []

    User = get_user_model()
    users = User.objects.filter(pk__in=user_ids).order_by("id")

    for user in users:
        try:
            refresh_user_currency_rates(user, force=force)
        except Exception as exc:  # pragma: no cover - defensive background safety.
            logger.exception(
                "Currency rates refresh failed in Celery task. task_id=%s user_id=%s",
                self.request.id,
                user.pk,
            )
            failed.append(
                {
                    "user_id": user.pk,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
        else:
            refreshed_ids.append(user.pk)

    result = {
        "requested_user_id": user_id,
        "processed_count": len(refreshed_ids) + len(failed),
        "refreshed_count": len(refreshed_ids),
        "failed_count": len(failed),
        "refreshed_user_ids": refreshed_ids,
        "failed": failed,
    }
    logger.info(
        "Currency rates task finished. task_id=%s processed=%s refreshed=%s failed=%s",
        self.request.id,
        result["processed_count"],
        result["refreshed_count"],
        result["failed_count"],
    )
    return result


@shared_task(bind=True, name="apps.finance.run_daily_finance_jobs")
def run_daily_finance_jobs_task(self) -> dict[str, Any]:
    planned_summary = run_due_planned_transactions()
    recurring_summary = run_due_recurring_transactions()

    return {
        "task_id": self.request.id,
        "planned": planned_summary.as_dict(),
        "recurring": recurring_summary.as_dict(),
    }


def _get_currency_rate_user_ids(*, user_id: int | None = None) -> list[int]:
    if user_id is not None:
        return [int(user_id)]

    return list(
        UserCurrency.objects
        .filter(Q(is_visible=True) | Q(is_primary=True))
        .values_list("user_id", flat=True)
        .distinct()
        .order_by("user_id")
    )

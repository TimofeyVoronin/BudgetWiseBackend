from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance.recurring_transactions import run_due_recurring_transactions


class Command(BaseCommand):
    help = (
        "Creates actual financial transactions for due recurring transactions. "
        "The command can be launched manually, by cron, or by a task scheduler."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="run_date",
            default=None,
            help="Run date in YYYY-MM-DD format. Defaults to the current local date.",
        )
        parser.add_argument(
            "--limit",
            dest="limit",
            type=int,
            default=None,
            help="Maximum number of recurring transactions to process.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Show due recurring transactions without creating operations.",
        )

    def handle(self, *args, **options):
        run_date = self._parse_run_date(options["run_date"])
        limit = options["limit"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer.")

        summary = run_due_recurring_transactions(
            run_date=run_date,
            limit=limit,
            dry_run=options["dry_run"],
        )
        data = summary.as_dict()

        self.stdout.write(
            self.style.SUCCESS(
                "Recurring transactions processing finished: "
                f"processed={data['processed_count']}, "
                f"created={data['created_count']}, "
                f"failed={data['failed_count']}, "
                f"skipped={data['skipped_count']}, "
                f"completed={data['completed_count']}."
            )
        )

        for item in data["items"]:
            scheduled_date = item["scheduled_date"] or "-"
            message = item["message"] or "-"
            transaction_id = item["transaction_id"] or "-"
            charge_id = item["charge_id"] or "-"
            error_code = item["error_code"] or "-"

            self.stdout.write(
                (
                    f"recurring_id={item['recurring_id']} "
                    f"scheduled_date={scheduled_date} "
                    f"status={item['status']} "
                    f"transaction_id={transaction_id} "
                    f"charge_id={charge_id} "
                    f"error_code={error_code} "
                    f"message={message}"
                )
            )

    def _parse_run_date(self, value: str | None) -> date | None:
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError("--date must be in YYYY-MM-DD format.") from exc

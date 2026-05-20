from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance.planned_transactions import run_due_planned_transactions


class Command(BaseCommand):
    help = (
        "Converts due planned transactions into actual financial transactions. "
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
            help="Maximum number of planned transactions to process.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Show due planned transactions without creating actual operations.",
        )

    def handle(self, *args, **options):
        run_date = self._parse_run_date(options["run_date"])
        limit = options["limit"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer.")

        summary = run_due_planned_transactions(
            run_date=run_date,
            limit=limit,
            dry_run=options["dry_run"],
        )
        data = summary.as_dict()

        self.stdout.write(
            self.style.SUCCESS(
                "Planned transactions conversion finished: "
                f"processed={data['processed_count']}, "
                f"converted={data['converted_count']}, "
                f"failed={data['failed_count']}, "
                f"skipped={data['skipped_count']}."
            )
        )

        for item in data["items"]:
            planned_date = item["planned_date"] or "-"
            message = item["message"] or "-"
            transaction_id = item["transaction_id"] or "-"
            error_code = item["error_code"] or "-"

            self.stdout.write(
                (
                    f"planned_id={item['planned_id']} "
                    f"planned_date={planned_date} "
                    f"status={item['status']} "
                    f"transaction_id={transaction_id} "
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

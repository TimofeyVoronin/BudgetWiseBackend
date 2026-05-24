from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DOMAIN_SYNC_MODE_READ_WRITE = "read_write"
DOMAIN_SYNC_MODE_READ_ONLY_SNAPSHOT = "read_only_snapshot"
DOMAIN_SYNC_MODE_OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class OfflineDomainArea:
    """Description of a functional area participating in offline-first sync."""

    key: str
    title: str
    description: str
    resources: tuple[str, ...] = field(default_factory=tuple)
    snapshots: tuple[str, ...] = field(default_factory=tuple)
    actions: tuple[str, ...] = field(default_factory=tuple)
    sync_mode: str = DOMAIN_SYNC_MODE_READ_WRITE
    priority: int = 100
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conflict_policy: str = "versioned_conflict_detection"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "resources": list(self.resources),
            "snapshots": list(self.snapshots),
            "actions": list(self.actions),
            "syncMode": self.sync_mode,
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "conflictPolicy": self.conflict_policy,
            "notes": list(self.notes),
        }


OFFLINE_DOMAIN_AREAS: tuple[OfflineDomainArea, ...] = (
    OfflineDomainArea(
        key="core-finance",
        title="Базовые финансовые данные",
        description="Счета, категории, операции, позиции операций и теги, необходимые для основной работы без сети.",
        resources=("accounts", "categories", "transactions", "tags"),
        actions=("create", "update", "delete"),
        priority=10,
        dependencies=(),
        notes=(
            "transaction line_items синхронизируются внутри ресурса transactions.",
            "categories и accounts должны быть доступны оффлайн до создания операций.",
        ),
    ),
    OfflineDomainArea(
        key="planning",
        title="Планирование и регулярные операции",
        description="Бюджеты, шаблоны операций, регулярные операции и плановые операции.",
        resources=("budgets", "transactionTemplates", "recurringTransactions", "plannedTransactions"),
        actions=("create", "update", "delete"),
        priority=20,
        dependencies=("accounts", "categories", "tags"),
        notes=(
            "plannedTransactions используются в финансовом календаре и прогнозе баланса.",
            "goals не входят в текущий offline-first scope.",
        ),
    ),
    OfflineDomainArea(
        key="reference-data",
        title="Справочники и настройки финансовых форм",
        description="Валюты пользователя и справочные данные, которые нужны для форм создания и редактирования.",
        resources=("currencies",),
        actions=("create", "update", "delete"),
        priority=30,
        dependencies=(),
        notes=(
            "Внешнее обновление курсов валют не выполняется оффлайн.",
            "Клиент может работать с последним сохранённым набором валют.",
        ),
    ),
    OfflineDomainArea(
        key="receipts",
        title="Фискальные чеки",
        description="Сохранённые чеки, позиции чеков и созданные из них операции.",
        resources=("receipts",),
        actions=(),
        sync_mode=DOMAIN_SYNC_MODE_READ_ONLY_SNAPSHOT,
        priority=40,
        dependencies=("transactions", "categories"),
        conflict_policy="server_authoritative",
        notes=(
            "Получение данных от внешнего провайдера чеков требует сети и не является offline-first действием.",
            "Созданные из чека операции синхронизируются через resources.transactions.",
        ),
    ),
    OfflineDomainArea(
        key="notifications",
        title="In-app уведомления",
        description="Центр уведомлений и локальные статусы прочтения/архивации.",
        resources=("notifications",),
        actions=(),
        sync_mode=DOMAIN_SYNC_MODE_READ_ONLY_SNAPSHOT,
        priority=50,
        dependencies=(),
        conflict_policy="server_authoritative",
        notes=(
            "Email и push-уведомления не входят в текущий scope.",
            "В текущей версии уведомления доступны как серверный снимок.",
        ),
    ),
    OfflineDomainArea(
        key="analytics-snapshots",
        title="Вычисляемые снимки интерфейса",
        description="Dashboard и финансовый календарь возвращаются как актуальные read-only снимки для отображения.",
        snapshots=("dashboard", "financialCalendar"),
        actions=(),
        sync_mode=DOMAIN_SYNC_MODE_READ_ONLY_SNAPSHOT,
        priority=60,
        dependencies=("accounts", "transactions", "plannedTransactions", "recurringTransactions"),
        conflict_policy="derived_snapshot",
        notes=(
            "Dashboard и financialCalendar нельзя отправлять в push как изменяемые ресурсы.",
            "На клиенте можно кэшировать последний снимок для оффлайн-просмотра.",
        ),
    ),
)

OUT_OF_SCOPE_DOMAIN_AREAS: tuple[OfflineDomainArea, ...] = (
    OfflineDomainArea(
        key="goals",
        title="Финансовые цели",
        description="Финансовые цели исключены из текущего offline-first scope.",
        resources=("goals",),
        sync_mode=DOMAIN_SYNC_MODE_OUT_OF_SCOPE,
        conflict_policy="not_supported",
        notes=("Ресурс не возвращается в bootstrap/pull и не принимается в push.",),
    ),
    OfflineDomainArea(
        key="reports",
        title="Отчёты и аналитика",
        description="Отчёты исключены из текущего offline-first scope.",
        resources=("reports",),
        sync_mode=DOMAIN_SYNC_MODE_OUT_OF_SCOPE,
        conflict_policy="not_supported",
        notes=("Отчёты строятся онлайн по серверным данным и не синхронизируются как offline-first ресурс.",),
    ),
    OfflineDomainArea(
        key="external-integrations",
        title="Внешние интеграции",
        description="Операции, которым нужен внешний сервис или сеть.",
        resources=("receiptProvider", "currencyRates", "email", "pushNotifications"),
        sync_mode=DOMAIN_SYNC_MODE_OUT_OF_SCOPE,
        conflict_policy="not_supported",
        notes=(
            "Провайдер чеков и обновление курсов валют требуют сети.",
            "Email и push пока остаются за пределами текущей реализации.",
        ),
    ),
)


def get_offline_domain_areas() -> list[dict[str, Any]]:
    return [area.as_dict() for area in OFFLINE_DOMAIN_AREAS]


def get_out_of_scope_domain_areas() -> list[dict[str, Any]]:
    return [area.as_dict() for area in OUT_OF_SCOPE_DOMAIN_AREAS]


def build_offline_domain_registry() -> dict[str, Any]:
    return {
        "domainAreas": get_offline_domain_areas(),
        "outOfScope": get_out_of_scope_domain_areas(),
    }


def get_writable_resources() -> list[str]:
    resources: list[str] = []
    for area in OFFLINE_DOMAIN_AREAS:
        if area.sync_mode != DOMAIN_SYNC_MODE_READ_WRITE:
            continue
        for resource in area.resources:
            if resource not in resources:
                resources.append(resource)
    return resources


def get_read_only_resources() -> list[str]:
    resources: list[str] = []
    for area in OFFLINE_DOMAIN_AREAS:
        if area.sync_mode != DOMAIN_SYNC_MODE_READ_ONLY_SNAPSHOT:
            continue
        for resource in area.resources:
            if resource not in resources:
                resources.append(resource)
    return resources


def get_read_only_snapshots() -> list[str]:
    snapshots: list[str] = []
    for area in OFFLINE_DOMAIN_AREAS:
        for snapshot in area.snapshots:
            if snapshot not in snapshots:
                snapshots.append(snapshot)
    return snapshots


def get_excluded_resources() -> list[str]:
    resources: list[str] = []
    for area in OUT_OF_SCOPE_DOMAIN_AREAS:
        for resource in area.resources:
            if resource not in resources:
                resources.append(resource)
    return resources

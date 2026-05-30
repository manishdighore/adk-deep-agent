"""Session-backed task ledger for adk-deep-agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LEDGER_STATE_KEY = "adk_deep_agent:todos"
TODO_TOOL_NAME = "todo"
MAX_TODOS = 100

TaskLedgerStatus = Literal["pending", "in_progress", "completed", "cancelled"]


class TaskLedgerItem(BaseModel):
    """One task item in the deep-agent ledger."""

    id: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)
    status: TaskLedgerStatus = "pending"

    @field_validator("id", "content")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value


class TaskLedgerSummary(BaseModel):
    """Counts for the current ledger."""

    total: int
    pending: int
    in_progress: int
    completed: int
    cancelled: int


class TaskLedgerResult(BaseModel):
    """Tool response returned by the built-in todo tool."""

    todos: list[TaskLedgerItem]
    summary: TaskLedgerSummary


def normalize_items(raw_items: object) -> list[TaskLedgerItem]:
    """Validate state payload into ledger items."""

    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        return []
    return [item if isinstance(item, TaskLedgerItem) else TaskLedgerItem.model_validate(item) for item in raw_items]


def serialize_items(items: list[TaskLedgerItem]) -> list[dict[str, str]]:
    """Serialize ledger items for ADK session state."""

    return [item.model_dump() for item in items]


def summarize_items(items: list[TaskLedgerItem]) -> TaskLedgerSummary:
    """Return summary counts for ledger items."""

    counts = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "cancelled": 0,
    }
    for item in items:
        counts[item.status] += 1
    return TaskLedgerSummary(total=len(items), **counts)


def ensure_unique_ids(items: list[TaskLedgerItem]) -> None:
    """Reject duplicate ledger IDs."""

    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item.id in seen:
            duplicates.add(item.id)
        seen.add(item.id)
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate todo id(s): {joined}")


def replace_items(items: list[TaskLedgerItem]) -> list[TaskLedgerItem]:
    """Validate and replace the ledger."""

    if len(items) > MAX_TODOS:
        raise ValueError(f"todo ledger cannot contain more than {MAX_TODOS} items")
    ensure_unique_ids(items)
    return items


def merge_items(
    current_items: list[TaskLedgerItem],
    updates: list[TaskLedgerItem],
) -> list[TaskLedgerItem]:
    """Merge updates by ID while retaining existing ledger order."""

    if not updates:
        return current_items
    ensure_unique_ids(updates)

    by_id = {item.id: item for item in current_items}
    order = [item.id for item in current_items]

    for item in updates:
        if item.id not in by_id:
            order.append(item.id)
        by_id[item.id] = item

    merged = [by_id[item_id] for item_id in order]
    if len(merged) > MAX_TODOS:
        raise ValueError(f"todo ledger cannot contain more than {MAX_TODOS} items")
    return merged


def active_items(items: list[TaskLedgerItem]) -> list[TaskLedgerItem]:
    """Return items that should be reinjected into model context."""

    return [item for item in items if item.status in {"pending", "in_progress"}]


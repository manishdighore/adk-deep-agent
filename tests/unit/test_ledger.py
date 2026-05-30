from types import SimpleNamespace
from inspect import getdoc

import pytest

from adk_deep_agent.ledger import LEDGER_STATE_KEY
from adk_deep_agent.ledger import TaskLedgerItem
from adk_deep_agent.ledger import active_items
from adk_deep_agent.tool import todo


def test_todo_description_matches_hermes_schema() -> None:
    assert getdoc(todo) == (
        "Manage your task list for the current session. Use for complex tasks "
        "with 3+ steps or when the user provides multiple tasks. "
        "Call with no parameters to read the current list.\n\n"
        "Writing:\n"
        "- Provide 'todos' array to create/update items\n"
        "- merge=false (default): replace the entire list with a fresh plan\n"
        "- merge=true: update existing items by id, add any new ones\n\n"
        "Each item: {id: string, content: string, "
        "status: pending|in_progress|completed|cancelled}\n"
        "List order is priority. Only ONE item in_progress at a time.\n"
        "Mark items completed immediately when done. If something fails, "
        "cancel it and add a revised item.\n\n"
        "Always returns the full current list."
    )


def test_todo_reads_empty_ledger() -> None:
    context = SimpleNamespace(state={})

    result = todo(tool_context=context)

    assert result["todos"] == []
    assert result["summary"]["total"] == 0


def test_todo_replaces_ledger() -> None:
    context = SimpleNamespace(state={})

    result = todo(
        todos=[
            TaskLedgerItem(id="t1", content="Plan work", status="completed"),
            TaskLedgerItem(id="t2", content="Implement work", status="in_progress"),
        ],
        tool_context=context,
    )

    assert result["summary"] == {
        "total": 2,
        "pending": 0,
        "in_progress": 1,
        "completed": 1,
        "cancelled": 0,
    }
    assert context.state[LEDGER_STATE_KEY][1]["id"] == "t2"


def test_todo_merges_by_id_and_preserves_order() -> None:
    context = SimpleNamespace(
        state={
            LEDGER_STATE_KEY: [
                {"id": "a", "content": "Old A", "status": "pending"},
                {"id": "b", "content": "Old B", "status": "pending"},
            ]
        }
    )

    result = todo(
        todos=[
            TaskLedgerItem(id="b", content="New B", status="completed"),
            TaskLedgerItem(id="c", content="New C", status="pending"),
        ],
        merge=True,
        tool_context=context,
    )

    assert [item["id"] for item in result["todos"]] == ["a", "b", "c"]
    assert result["todos"][1]["content"] == "New B"
    assert context.state[LEDGER_STATE_KEY][2]["id"] == "c"


def test_todo_rejects_duplicate_ids_without_state_mutation() -> None:
    existing = [{"id": "a", "content": "Old A", "status": "pending"}]
    context = SimpleNamespace(state={LEDGER_STATE_KEY: [*existing]})

    with pytest.raises(ValueError, match="duplicate todo"):
        todo(
            todos=[
                TaskLedgerItem(id="x", content="First", status="pending"),
                TaskLedgerItem(id="x", content="Second", status="pending"),
            ],
            tool_context=context,
        )

    assert context.state[LEDGER_STATE_KEY] == existing


def test_active_items_excludes_completed_and_cancelled() -> None:
    items = [
        TaskLedgerItem(id="a", content="A", status="pending"),
        TaskLedgerItem(id="b", content="B", status="in_progress"),
        TaskLedgerItem(id="c", content="C", status="completed"),
        TaskLedgerItem(id="d", content="D", status="cancelled"),
    ]

    assert [item.id for item in active_items(items)] == ["a", "b"]

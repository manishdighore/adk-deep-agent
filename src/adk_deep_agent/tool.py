"""Built-in ADK tools for adk-deep-agent."""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from .ledger import LEDGER_STATE_KEY
from .ledger import TaskLedgerItem
from .ledger import TaskLedgerResult
from .ledger import merge_items
from .ledger import normalize_items
from .ledger import replace_items
from .ledger import serialize_items
from .ledger import summarize_items


def todo(
    todos: list[TaskLedgerItem] | None = None,
    merge: bool = False,
    tool_context: ToolContext | None = None,
) -> dict:
    """Manage your task list for the current session. Use for complex tasks with 3+ steps or when the user provides multiple tasks. Call with no parameters to read the current list.

    Writing:
    - Provide 'todos' array to create/update items
    - merge=false (default): replace the entire list with a fresh plan
    - merge=true: update existing items by id, add any new ones

    Each item: {id: string, content: string, status: pending|in_progress|completed|cancelled}
    List order is priority. Only ONE item in_progress at a time.
    Mark items completed immediately when done. If something fails, cancel it and add a revised item.

    Always returns the full current list.
    """

    if tool_context is None:
        raise ValueError("todo tool requires ADK ToolContext")

    current_items = normalize_items(tool_context.state.get(LEDGER_STATE_KEY))
    if todos is None:
        result_items = current_items
    elif merge:
        result_items = merge_items(current_items, todos)
        tool_context.state[LEDGER_STATE_KEY] = serialize_items(result_items)
    else:
        result_items = replace_items(todos)
        tool_context.state[LEDGER_STATE_KEY] = serialize_items(result_items)

    result = TaskLedgerResult(
        todos=result_items,
        summary=summarize_items(result_items),
    )
    return result.model_dump()


def create_todo_tool() -> FunctionTool:
    """Create the built-in todo function tool."""

    return FunctionTool(todo)

"""Root-agent callbacks for adk-agent-harness."""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .ledger import LEDGER_STATE_KEY
from .ledger import TODO_TOOL_NAME
from .ledger import active_items
from .ledger import normalize_items


def format_active_ledger_context(raw_items: object) -> str | None:
    """Format active ledger items for root model-context injection."""

    items = active_items(normalize_items(raw_items))
    if not items:
        return None

    lines = [
        "Current task ledger. Continue from this state; do not repeat completed work.",
    ]
    for item in items:
        lines.append(f"- [{item.status}] {item.id}: {item.content}")
    return "\n".join(lines)


def inject_active_ledger(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Inject active task-ledger items before each root model request."""

    ledger_context = format_active_ledger_context(
        callback_context.state.get(LEDGER_STATE_KEY)
    )
    if ledger_context:
        llm_request.append_instructions([ledger_context])
    return None


def guard_multiple_todo_writes(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Reject competing todo writes from a single model response.

    ADK may dispatch multiple function calls from one model message in
    parallel. Returning a replacement response here prevents those writes from
    reaching the tool executor.
    """

    if llm_response.partial or not llm_response.content or not llm_response.content.parts:
        return None

    write_calls = []
    for part in llm_response.content.parts:
        call = part.function_call
        if not call or call.name != TODO_TOOL_NAME:
            continue
        args = dict(call.args or {})
        if args.get("todos") is not None:
            write_calls.append(call)

    if len(write_calls) <= 1:
        return None

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        "Rejected multiple todo write calls in one model "
                        "response. Update the task ledger with a single todo "
                        "write call and try again."
                    )
                )
            ],
        )
    )


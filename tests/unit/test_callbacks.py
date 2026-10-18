from types import SimpleNamespace

from adk_agent_harness.callbacks import guard_multiple_todo_writes
from adk_agent_harness.callbacks import inject_active_ledger
from adk_agent_harness.ledger import LEDGER_STATE_KEY
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def test_inject_active_ledger_appends_system_instruction() -> None:
    context = SimpleNamespace(
        state={
            LEDGER_STATE_KEY: [
                {"id": "a", "content": "Do A", "status": "pending"},
                {"id": "b", "content": "Done B", "status": "completed"},
            ]
        }
    )
    request = LlmRequest()

    inject_active_ledger(context, request)

    assert "Do A" in request.config.system_instruction
    assert "Done B" not in request.config.system_instruction


def test_inject_active_ledger_noops_without_active_items() -> None:
    context = SimpleNamespace(state={LEDGER_STATE_KEY: []})
    request = LlmRequest()

    inject_active_ledger(context, request)

    assert request.config.system_instruction is None


def test_guard_multiple_todo_writes_replaces_response() -> None:
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="todo",
                    args={"todos": [{"id": "a", "content": "A"}]},
                ),
                types.Part.from_function_call(
                    name="todo",
                    args={"todos": [{"id": "b", "content": "B"}]},
                ),
            ],
        )
    )

    guarded = guard_multiple_todo_writes(SimpleNamespace(state={}), response)

    assert guarded is not None
    assert guarded.content.parts[0].text.startswith("Rejected multiple todo write")


def test_guard_allows_single_todo_write() -> None:
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="todo",
                    args={"todos": [{"id": "a", "content": "A"}]},
                ),
            ],
        )
    )

    assert guard_multiple_todo_writes(SimpleNamespace(state={}), response) is None


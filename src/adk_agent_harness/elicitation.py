"""Structured user-elicitation helpers over ADK request_input."""

from __future__ import annotations

from typing import Any

from google.adk.events.event import Event
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

REQUEST_INPUT_TOOL_NAME = "adk_request_input"

ELICITATION_TOOL_GUIDANCE = """You have a built-in `adk_request_input` tool for structured user elicitation.

Use it only when required information cannot be inferred safely. Prefer one
request with an object JSON schema containing all related questions. Use
standard JSON Schema: `title` and `description` for labels and help text,
`enum` for selectable options, `boolean` for confirmations, arrays for
multi-select, and `required` for mandatory answers. Do not continue until the
tool returns the user's structured response.
"""


class ElicitationRequest(BaseModel):
    """Stable UI-facing projection of an ADK request_input interruption."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    message: str
    response_schema: dict[str, Any] | None = None
    invocation_id: str
    author: str
    raw_event: Event = Field(exclude=True)


def project_elicitation_event(event: Event) -> ElicitationRequest | None:
    """Project an ADK request_input function call for a client UI."""

    long_running_ids = set(event.long_running_tool_ids or [])
    for call in event.get_function_calls():
        if call.name != REQUEST_INPUT_TOOL_NAME:
            continue
        if long_running_ids and call.id not in long_running_ids:
            continue
        args = dict(call.args or {})
        schema = args.get("response_schema")
        return ElicitationRequest(
            id=call.id,
            message=str(args.get("message", "")),
            response_schema=dict(schema) if isinstance(schema, dict) else None,
            invocation_id=event.invocation_id,
            author=event.author,
            raw_event=event,
        )
    return None


def create_elicitation_response(
    request: ElicitationRequest,
    answers: Any,
) -> types.Content:
    """Build the user-role FunctionResponse that resumes an elicitation."""

    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=request.id,
                    name=REQUEST_INPUT_TOOL_NAME,
                    response={"result": answers},
                )
            )
        ],
    )

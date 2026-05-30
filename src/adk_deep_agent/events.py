"""Subagent event projection helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from google.adk.events.event import Event
from pydantic import BaseModel, ConfigDict, Field

SubagentEventKind = Literal[
    "message",
    "tool_call",
    "tool_result",
    "complete",
    "error",
]


class SubagentEvent(BaseModel):
    """Stable package projection over a raw ADK subagent event."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    child_agent: str
    kind: SubagentEventKind
    content: dict[str, Any]
    raw_event: Event = Field(exclude=True)


def _part_summary(event: Event) -> tuple[SubagentEventKind, dict[str, Any]]:
    if event.error_code or event.error_message:
        return "error", {
            "error_code": event.error_code,
            "error_message": event.error_message,
        }

    function_calls = event.get_function_calls()
    if function_calls:
        return "tool_call", {
            "calls": [
                {"name": call.name, "args": dict(call.args or {})}
                for call in function_calls
            ]
        }

    function_responses = event.get_function_responses()
    if function_responses:
        return "tool_result", {
            "responses": [
                {"name": response.name, "response": response.response}
                for response in function_responses
            ]
        }

    texts: list[str] = []
    thoughts: list[str] = []
    if event.content and event.content.parts:
        for part in event.content.parts:
            if not part.text:
                continue
            if part.thought:
                thoughts.append(part.text)
            else:
                texts.append(part.text)

    if event.output is not None:
        return "complete", {
            "output": event.output,
            "text": "\n".join(texts),
            "thoughts": thoughts,
        }

    return "message", {
        "text": "\n".join(texts),
        "thoughts": thoughts,
    }


def project_subagent_event(
    event: Event,
    *,
    root_agent_name: str,
    child_agent_names: Iterable[str] = (),
) -> SubagentEvent | None:
    """Project one raw ADK event when it belongs to a child agent."""

    child_names = set(child_agent_names)
    author = event.author
    if not author or author in {root_agent_name, "user"}:
        return None
    if child_names and author not in child_names:
        path = getattr(event.node_info, "path", "") or ""
        if not any(
            f"/{name}@" in path or path.startswith(f"{name}@")
            for name in child_names
        ):
            return None

    kind, content = _part_summary(event)
    content.update(
        {
            "author": author,
            "branch": event.branch,
            "node_path": getattr(event.node_info, "path", None),
        }
    )
    return SubagentEvent(
        child_agent=author,
        kind=kind,
        content=content,
        raw_event=event,
    )


def iter_subagent_events(
    events: Iterable[Event],
    *,
    root_agent_name: str,
    child_agent_names: Iterable[str] = (),
) -> list[SubagentEvent]:
    """Project all subagent events from a raw ADK event iterable."""

    projected: list[SubagentEvent] = []
    for event in events:
        subagent_event = project_subagent_event(
            event,
            root_agent_name=root_agent_name,
            child_agent_names=child_agent_names,
        )
        if subagent_event is not None:
            projected.append(subagent_event)
    return projected

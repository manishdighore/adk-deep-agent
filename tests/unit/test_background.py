from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from adk_agent_harness import ModelSpec
from adk_agent_harness import SpawnConfig
from adk_agent_harness import cancel_background_task
from adk_agent_harness import create_deep_agent
from adk_agent_harness import get_background_task
from adk_agent_harness import list_background_tasks
from adk_agent_harness import stream_background_task_events
from adk_agent_harness import wait_for_background_task
from adk_agent_harness.subagents import SPAWN_TOOL_NAME
from google.adk.apps.app import App
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.events.event import Event
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types


class ScriptedModel(BaseLlm):
    """Fake ADK model that replays scripted responses and records requests."""

    model: str = "scripted-model"
    responses: list[Any]
    requests: list[LlmRequest] = []

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            parts = [types.Part.from_text(text=response)]
        elif isinstance(response, types.Part):
            parts = [response]
        else:
            parts = response
        yield LlmResponse(content=types.Content(role="model", parts=parts))


def _call(name: str, args: dict[str, Any]) -> types.Part:
    return types.Part.from_function_call(name=name, args=args)


def _thought(text: str) -> types.Part:
    return types.Part(text=text, thought=True)


def _to_agui(events: list[Event]) -> list[tuple[str, str]]:
    """Test-only sketch of translating raw ADK events into AG-UI event types."""

    translated: list[tuple[str, str]] = []
    for event in events:
        for part in event.content.parts if event.content else []:
            if part.function_call:
                translated.append(("TOOL_CALL_START", f"{event.author}:{part.function_call.name}"))
            elif part.function_response:
                translated.append(("TOOL_CALL_RESULT", f"{event.author}:{part.function_response.name}"))
            elif part.text and part.thought:
                translated.append(("THINKING_TEXT_MESSAGE_CONTENT", event.author))
            elif part.text:
                translated.append(("TEXT_MESSAGE_CONTENT", event.author))
    return translated


class Harness:
    def __init__(self, app: App, state: dict[str, Any] | None = None) -> None:
        self.app = app
        self.state = state
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app=app,
            artifact_service=InMemoryArtifactService(),
            session_service=self.session_service,
            memory_service=InMemoryMemoryService(),
        )
        self.session_id: str | None = None

    async def turn(self, text: str) -> list[Event]:
        if self.session_id is None:
            session = await self.session_service.create_session(
                app_name=self.app.name,
                user_id="test",
                state=self.state,
            )
            self.session_id = session.id
        return [
            event
            async for event in self.runner.run_async(
                user_id="test",
                session_id=self.session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)],
                ),
            )
        ]

    async def session_state(self) -> dict[str, Any]:
        session = await self.session_service.get_session(
            app_name=self.app.name,
            user_id="test",
            session_id=self.session_id,
        )
        return dict(session.state)


def _spawn_responses(events: list[Event]) -> list[dict[str, Any]]:
    return [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]


def _system_instruction(request: LlmRequest) -> str:
    return str(request.config.system_instruction or "")


def _gated_lookup(gate: asyncio.Event):
    async def lookup(query: str) -> dict:
        """Look up a fact."""
        await gate.wait()
        return {"answer": f"facts about {query}"}

    return lookup


def _app(root_model: ScriptedModel, child_model: ScriptedModel, tools=()) -> App:
    return create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        tools=list(tools),
        available_models=[ModelSpec(id="child", model_client=child_model)],
        spawn=SpawnConfig(enabled=True),
    )


@pytest.mark.asyncio
async def test_foreground_spawn_streams_child_events_in_root_stream() -> None:
    gate = asyncio.Event()
    gate.set()
    child_model = ScriptedModel(
        requests=[],
        responses=[
            _call("lookup", {"query": "adk"}),
            [_thought("checking the facts"), types.Part.from_text(text="adk facts")],
        ],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "researcher",
                    "goal": "Research ADK.",
                    "model": "child",
                    "tool_names": ["lookup"],
                },
            ),
            "root done",
        ],
    )
    harness = Harness(_app(root_model, child_model, tools=[_gated_lookup(gate)]))

    events = await harness.turn("start")

    assert _spawn_responses(events)[0]["status"] == "completed"
    assert _spawn_responses(events)[0]["result"] == "adk facts"
    assert _to_agui(events) == [
        ("TOOL_CALL_START", f"root:{SPAWN_TOOL_NAME}"),
        ("TOOL_CALL_START", "researcher:lookup"),
        ("TOOL_CALL_RESULT", "researcher:lookup"),
        ("THINKING_TEXT_MESSAGE_CONTENT", "researcher"),
        ("TEXT_MESSAGE_CONTENT", "researcher"),
        ("TOOL_CALL_RESULT", f"root:{SPAWN_TOOL_NAME}"),
        ("TEXT_MESSAGE_CONTENT", "root"),
    ]


@pytest.mark.asyncio
async def test_background_spawn_returns_immediately_and_streams_child_events() -> None:
    gate = asyncio.Event()
    child_model = ScriptedModel(
        requests=[],
        responses=[
            _call("lookup", {"query": "adk"}),
            [_thought("checking the facts"), types.Part.from_text(text="adk facts")],
        ],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "researcher",
                    "goal": "Research ADK.",
                    "model": "child",
                    "tool_names": ["lookup"],
                    "background": True,
                },
            ),
            "root keeps working",
        ],
    )
    harness = Harness(_app(root_model, child_model, tools=[_gated_lookup(gate)]))

    root_events = await harness.turn("start")

    # The root turn finished while the child is still blocked in its tool.
    response = _spawn_responses(root_events)[0]
    assert response["status"] == "running"
    task_id = response["task_id"]
    assert get_background_task(task_id).status == "running"
    assert [task.task_id for task in list_background_tasks(session_id=harness.session_id)] == [task_id]
    assert _to_agui(root_events) == [
        ("TOOL_CALL_START", f"root:{SPAWN_TOOL_NAME}"),
        ("TOOL_CALL_RESULT", f"root:{SPAWN_TOOL_NAME}"),
        ("TEXT_MESSAGE_CONTENT", "root"),
    ]

    gate.set()
    child_events = [event async for event in stream_background_task_events(task_id)]
    task = await wait_for_background_task(task_id)

    assert task.status == "completed"
    assert task.result == "adk facts"
    assert _to_agui(child_events) == [
        ("TOOL_CALL_START", "researcher:lookup"),
        ("TOOL_CALL_RESULT", "researcher:lookup"),
        ("THINKING_TEXT_MESSAGE_CONTENT", "researcher"),
        ("TEXT_MESSAGE_CONTENT", "researcher"),
    ]
    # A late subscriber replays the same raw stream.
    replayed = [event async for event in stream_background_task_events(task_id)]
    assert [event.id for event in replayed] == [event.id for event in child_events]


@pytest.mark.asyncio
async def test_background_status_and_result_are_injected_into_root_context() -> None:
    gate = asyncio.Event()
    child_model = ScriptedModel(
        requests=[],
        responses=[_call("lookup", {"query": "adk"}), "adk facts"],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "researcher",
                    "goal": "Research ADK.",
                    "model": "child",
                    "tool_names": ["lookup"],
                    "background": True,
                },
            ),
            "started research",
            "still waiting",
            "here are the results",
            "nothing new",
        ],
    )
    harness = Harness(_app(root_model, child_model, tools=[_gated_lookup(gate)]))

    task_id = _spawn_responses(await harness.turn("start"))[0]["task_id"]

    await harness.turn("status?")
    running_instruction = _system_instruction(root_model.requests[2])
    assert "Still running" in running_instruction
    assert task_id in running_instruction

    gate.set()
    await wait_for_background_task(task_id)

    await harness.turn("any results?")
    finished_instruction = _system_instruction(root_model.requests[3])
    assert "Finished since your last turn" in finished_instruction
    assert "adk facts" in finished_instruction
    assert "Still running" not in finished_instruction

    await harness.turn("anything else?")
    assert "Background subagent updates" not in _system_instruction(root_model.requests[4])


@pytest.mark.asyncio
async def test_background_child_is_isolated_from_root_state() -> None:
    seen: dict[str, Any] = {}

    def inspect_state(tool_context: ToolContext) -> dict:
        """Inspect and write session state."""
        seen["root_secret"] = tool_context.state.get("root_secret")
        tool_context.state["child_key"] = "child value"
        return {"ok": True}

    child_model = ScriptedModel(
        requests=[],
        responses=[_call("inspect_state", {}), "inspected"],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "inspector",
                    "goal": "Inspect state.",
                    "model": "child",
                    "tool_names": ["inspect_state"],
                    "background": True,
                },
            ),
            "started",
        ],
    )
    harness = Harness(
        _app(root_model, child_model, tools=[inspect_state]),
        state={"root_secret": "do not share"},
    )

    task_id = _spawn_responses(await harness.turn("start"))[0]["task_id"]
    task = await wait_for_background_task(task_id)

    assert task.status == "completed"
    assert seen["root_secret"] is None
    root_state = await harness.session_state()
    assert root_state["root_secret"] == "do not share"
    assert "child_key" not in root_state


@pytest.mark.asyncio
async def test_background_child_failure_is_reported() -> None:
    child_model = ScriptedModel(
        requests=[],
        responses=[RuntimeError("model unavailable")],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "flaky",
                    "goal": "Try something.",
                    "model": "child",
                    "background": True,
                },
            ),
            "started",
            "it failed",
        ],
    )
    harness = Harness(_app(root_model, child_model))

    task_id = _spawn_responses(await harness.turn("start"))[0]["task_id"]
    task = await wait_for_background_task(task_id)

    assert task.status == "failed"
    assert "model unavailable" in task.error
    await harness.turn("status?")
    # The failure may surface on the root's next request in the same turn or
    # the next turn, depending on timing, but it is reported exactly once.
    reports = [
        request
        for request in root_model.requests
        if "model unavailable" in _system_instruction(request)
    ]
    assert len(reports) == 1
    assert "failed" in _system_instruction(reports[0])


@pytest.mark.asyncio
async def test_background_task_can_be_cancelled() -> None:
    gate = asyncio.Event()
    child_model = ScriptedModel(
        requests=[],
        responses=[_call("lookup", {"query": "adk"}), "never reached"],
    )
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {
                    "name": "researcher",
                    "goal": "Research ADK.",
                    "model": "child",
                    "tool_names": ["lookup"],
                    "background": True,
                },
            ),
            "started",
        ],
    )
    harness = Harness(_app(root_model, child_model, tools=[_gated_lookup(gate)]))

    task_id = _spawn_responses(await harness.turn("start"))[0]["task_id"]
    await asyncio.sleep(0)

    assert cancel_background_task(task_id) is True
    task = await wait_for_background_task(task_id)
    assert task.status == "cancelled"
    assert cancel_background_task(task_id) is False

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from adk_deep_agent import SpawnConfig
from adk_deep_agent import SubAgentSpec
from adk_deep_agent import create_deep_agent
from adk_deep_agent import iter_subagent_events
from adk_deep_agent.subagents import SPAWN_TOOL_NAME
from google.adk.apps.app import App
from google.adk.events.event import Event
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


class FakeModel(BaseLlm):
    """Tiny ADK BaseLlm-like mock that returns configured responses."""

    responses: list[Any]
    response_index: int = 0
    model: str = "fake-model"

    @property
    def supported_models(self) -> list[str]:
        return ["fake-model"]

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        response = self.responses[self.response_index]
        self.response_index += 1
        if isinstance(response, LlmResponse):
            yield response
            return
        if isinstance(response, str):
            parts = [types.Part.from_text(text=response)]
        elif isinstance(response, types.Part):
            parts = [response]
        else:
            parts = response
        yield LlmResponse(content=types.Content(role="model", parts=parts))


def _function_call(name: str, args: dict[str, Any]) -> types.Part:
    return types.Part.from_function_call(name=name, args=args)


def _finish_task(args: dict[str, Any]) -> types.Part:
    return types.Part.from_function_call(name="finish_task", args=args)


async def _run_app(app: App) -> list[Event]:
    from google.adk.runners import Runner
    from google.adk.artifacts.in_memory_artifact_service import (
        InMemoryArtifactService,
    )
    from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=app.name, user_id="test")
    runner = Runner(
        app=app,
        artifact_service=InMemoryArtifactService(),
        session_service=session_service,
        memory_service=InMemoryMemoryService(),
    )
    events: list[Event] = []
    async for event in runner.run_async(
        user_id="test",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="start")],
        ),
    ):
        events.append(event)
    return events


def test_factory_attaches_prebuilt_single_turn_subagent() -> None:
    app = create_deep_agent(
        name="root",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        subagents=[
            SubAgentSpec(
                name="researcher",
                goal="Research the request.",
                mode="single_turn",
            )
        ],
    )

    assert [agent.name for agent in app.root_agent.sub_agents] == ["researcher"]
    assert app.root_agent.sub_agents[0].mode == "single_turn"
    assert app.root_agent.sub_agents[0].description == "Research the request."


def test_factory_adds_spawn_tool_only_when_enabled() -> None:
    without_spawn = create_deep_agent(
        name="root_no_spawn",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
    )
    with_spawn = create_deep_agent(
        name="root_spawn",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    assert not any(
        getattr(tool, "name", "") == SPAWN_TOOL_NAME
        for tool in without_spawn.root_agent.tools
    )
    assert any(
        getattr(tool, "name", "") == SPAWN_TOOL_NAME
        for tool in with_spawn.root_agent.tools
    )


@pytest.mark.asyncio
async def test_prebuilt_single_turn_child_raw_events_are_streamed() -> None:
    child_model = FakeModel(responses=["child done"])
    root_model = FakeModel(
        responses=[
            _function_call("researcher", {"request": "research"}),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        subagents=[
            SubAgentSpec(
                name="researcher",
                goal="Research.",
                model_client=child_model,
                mode="single_turn",
            )
        ],
    )

    events = await _run_app(app)

    assert any(event.author == "researcher" for event in events)
    projected = iter_subagent_events(
        events,
        root_agent_name="root",
        child_agent_names=["researcher"],
    )
    assert projected
    assert projected[0].child_agent == "researcher"


@pytest.mark.asyncio
async def test_prebuilt_task_child_raw_events_are_streamed() -> None:
    child_model = FakeModel(
        responses=[_finish_task({"result": "child task done"})]
    )
    root_model = FakeModel(
        responses=[
            _function_call("worker", {"request": "work"}),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        subagents=[
            SubAgentSpec(
                name="worker",
                goal="Work.",
                model_client=child_model,
                mode="task",
            )
        ],
    )

    events = await _run_app(app)

    child_events = [event for event in events if event.author == "worker"]
    assert child_events
    assert any(
        call.name == "finish_task"
        for event in child_events
        for call in event.get_function_calls()
    )


@pytest.mark.asyncio
async def test_spawned_single_turn_child_raw_events_are_streamed() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_researcher",
                    "goal": "Research.",
                    "context": "Use concise output.",
                },
            ),
            "spawned child done",
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    events = await _run_app(app)

    assert any(event.author == "temp_researcher" for event in events)
    assert iter_subagent_events(
        events,
        root_agent_name="root",
        child_agent_names=["temp_researcher"],
    )


@pytest.mark.asyncio
async def test_spawn_tool_rejects_unknown_tool_name() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_worker",
                    "goal": "Work.",
                    "tool_names": ["missing_tool"],
                },
            ),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    events = await _run_app(app)

    responses = [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]
    assert responses
    assert responses[0]["status"] == "error"
    assert "unknown tool" in responses[0]["error"]


@pytest.mark.asyncio
async def test_spawned_task_child_raw_events_are_streamed() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_task_worker",
                    "goal": "Finish a task.",
                    "mode": "task",
                },
            ),
            _finish_task({"result": "spawned task done"}),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    events = await _run_app(app)

    child_events = [
        event for event in events if event.author == "temp_task_worker"
    ]
    assert child_events
    assert any(
        call.name == "finish_task"
        for event in child_events
        for call in event.get_function_calls()
    )


@pytest.mark.asyncio
async def test_spawned_task_that_asks_user_returns_waiting_status() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_clarifier",
                    "goal": "Clarify the task.",
                    "mode": "task",
                },
            ),
            "I need one clarification from the user.",
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    events = await _run_app(app)

    responses = [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]
    assert responses
    assert responses[0]["status"] == "waiting_for_user"
    assert "clarification" in responses[0]["message"]

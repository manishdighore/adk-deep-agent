from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from adk_agent_harness import SpawnConfig
from adk_agent_harness import ModelSpec
from adk_agent_harness import SubAgentSpec
from adk_agent_harness import create_deep_agent
from adk_agent_harness.subagents import SPAWN_TOOL_NAME
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

    child_events = [event for event in events if event.author == "researcher"]
    assert child_events
    assert all("researcher@" in (event.branch or "") for event in child_events)
    assert any(
        part.text == "child done"
        for event in child_events
        for part in (event.content.parts if event.content else [])
    )


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

    child_events = [event for event in events if event.author == "temp_researcher"]
    assert child_events
    assert all("temp_researcher@" in (event.branch or "") for event in child_events)
    assert any(
        part.text == "spawned child done"
        for event in child_events
        for part in (event.content.parts if event.content else [])
    )


@pytest.mark.asyncio
async def test_spawned_child_can_select_a_registered_model() -> None:
    child_model = FakeModel(responses=["selected model child done"])
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "specialist",
                    "goal": "Handle difficult work.",
                    "model": "strong",
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
        available_models=[
            ModelSpec(
                id="strong",
                model_client=child_model,
                description="Use for difficult reasoning.",
            )
        ],
    )

    events = await _run_app(app)

    assert child_model.response_index == 1
    responses = [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]
    assert responses[0]["status"] == "completed"
    assert responses[0]["model"] == "strong"
    assert "`strong` - Use for difficult reasoning." in app.root_agent.instruction


@pytest.mark.asyncio
async def test_spawn_tool_rejects_unknown_model() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "specialist",
                    "goal": "Work.",
                    "model": "missing",
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
    assert responses[0]["status"] == "error"
    assert responses[0]["error"] == "unknown model: missing"


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


class RecordingModel(FakeModel):
    requests: list[LlmRequest] = []

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        async for response in super().generate_content_async(llm_request, stream):
            yield response


def _spawn_tool(app: App):
    return next(
        tool
        for tool in app.root_agent.tools
        if getattr(tool, "name", "") == SPAWN_TOOL_NAME
    )


def test_spawn_tool_does_not_expose_a_mode_argument() -> None:
    app = create_deep_agent(
        name="root",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        spawn=SpawnConfig(enabled=True),
    )

    declaration = _spawn_tool(app)._get_declaration()
    schema = declaration.parameters_json_schema or {}
    properties = schema.get("properties") or (
        declaration.parameters.properties if declaration.parameters else {}
    )
    assert "goal" in properties
    assert "mode" not in properties


@pytest.mark.asyncio
async def test_spawned_child_runs_single_turn_on_function_call_branch() -> None:
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {"name": "temp_worker", "goal": "Do the work."},
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

    spawn_call_id = next(
        call.id
        for event in events
        for call in event.get_function_calls()
        if call.name == SPAWN_TOOL_NAME
    )
    child_events = [event for event in events if event.author == "temp_worker"]
    assert child_events
    assert all(
        event.branch and event.branch.endswith(f"temp_worker@{spawn_call_id}")
        for event in child_events
    )
    responses = [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]
    assert responses[0]["status"] == "completed"
    assert responses[0]["result"] == "spawned child done"


@pytest.mark.asyncio
async def test_spawned_child_receives_goal_and_context_as_request() -> None:
    child_model = RecordingModel(requests=[], responses=["child done"])
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_writer",
                    "goal": "Draft the summary.",
                    "context": "Audience is the finance team.",
                    "model": "child",
                },
            ),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        available_models=[ModelSpec(id="child", model_client=child_model)],
        spawn=SpawnConfig(enabled=True),
    )

    await _run_app(app)

    request = child_model.requests[0]
    request_text = "\n".join(
        part.text
        for content in request.contents
        for part in (content.parts or [])
        if part.text
    )
    assert "Goal: Draft the summary." in request_text
    assert "Audience is the finance team." in request_text
    instruction = str(request.config.system_instruction)
    assert "Draft the summary." not in instruction
    assert "cannot ask the user" in instruction


@pytest.mark.asyncio
async def test_spawned_child_cannot_be_given_request_input() -> None:
    from google.adk.tools import request_input

    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_asker",
                    "goal": "Ask the user.",
                    "tool_names": ["adk_request_input"],
                },
            ),
            "root done",
        ]
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        elicitation=True,
        spawn=SpawnConfig(
            enabled=True,
            tools={"adk_request_input": request_input},
        ),
    )

    events = await _run_app(app)

    responses = [
        response.response
        for event in events
        for response in event.get_function_responses()
        if response.name == SPAWN_TOOL_NAME
    ]
    assert responses[0]["status"] == "error"
    assert "unknown tool" in responses[0]["error"]

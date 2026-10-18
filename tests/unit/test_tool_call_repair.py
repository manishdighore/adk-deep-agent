from __future__ import annotations

import asyncio
from typing import Any

import pytest

from adk_agent_harness import ModelSpec
from adk_agent_harness import REQUEST_INPUT_TOOL_NAME
from adk_agent_harness import SpawnConfig
from adk_agent_harness import ToolCallRepairPlugin
from adk_agent_harness import create_deep_agent
from adk_agent_harness import repair_dangling_tool_calls
from adk_agent_harness import wait_for_background_task
from adk_agent_harness.subagents import SPAWN_TOOL_NAME
from adk_agent_harness.tool_call_repair import INTERRUPTED_TOOL_RESULT
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from test_background import Harness
from test_background import ScriptedModel
from test_background import _call


def _call_part(name: str, call_id: str | None = None) -> types.Part:
    return types.Part(function_call=types.FunctionCall(id=call_id, name=name, args={}))


def _response_part(name: str, call_id: str | None = None) -> types.Part:
    return types.Part(
        function_response=types.FunctionResponse(id=call_id, name=name, response={"ok": True})
    )


def _text(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


def _unanswered_count(request: LlmRequest) -> int:
    """Number of calls the model received without a matching result."""

    probe = [content.model_copy(deep=True) for content in request.contents]
    return repair_dangling_tool_calls(probe)


def _interrupted_results(request: LlmRequest) -> list[types.FunctionResponse]:
    return [
        part.function_response
        for content in request.contents
        for part in content.parts or []
        if part.function_response
        and part.function_response.response == INTERRUPTED_TOOL_RESULT
    ]


# --- Pure function -----------------------------------------------------------


def test_unanswered_call_gets_a_synthetic_result_after_it() -> None:
    contents = [
        _text("user", "do it"),
        types.Content(role="model", parts=[_call_part("lookup")]),
        _text("user", "are you there?"),
    ]

    assert repair_dangling_tool_calls(contents) == 1

    assert [content.role for content in contents] == ["user", "model", "user", "user"]
    synthetic = contents[2].parts[0].function_response
    assert synthetic.name == "lookup"
    assert synthetic.response == INTERRUPTED_TOOL_RESULT


def test_partially_answered_parallel_calls_are_completed_in_place() -> None:
    contents = [
        types.Content(role="model", parts=[_call_part("a"), _call_part("b")]),
        types.Content(role="user", parts=[_response_part("a")]),
    ]

    assert repair_dangling_tool_calls(contents) == 1

    assert len(contents) == 2
    names = [part.function_response.name for part in contents[1].parts]
    assert names == ["a", "b"]


def test_answered_calls_are_left_alone() -> None:
    contents = [
        types.Content(role="model", parts=[_call_part("a"), _call_part("a")]),
        types.Content(role="user", parts=[_response_part("a"), _response_part("a")]),
        _text("model", "done"),
    ]
    before = [content.model_dump() for content in contents]

    assert repair_dangling_tool_calls(contents) == 0
    assert [content.model_dump() for content in contents] == before


def test_provider_call_ids_are_matched_and_preserved() -> None:
    contents = [
        types.Content(
            role="model",
            parts=[_call_part("search", "call_1"), _call_part("search", "call_2")],
        ),
        types.Content(role="user", parts=[_response_part("search", "call_2")]),
    ]

    assert repair_dangling_tool_calls(contents) == 1

    ids = [part.function_response.id for part in contents[1].parts]
    assert ids == ["call_2", "call_1"]


def test_repair_never_mutates_the_original_content_objects() -> None:
    call = types.Content(role="model", parts=[_call_part("a"), _call_part("b")])
    partial = types.Content(role="user", parts=[_response_part("a")])
    contents = [call, partial]

    repair_dangling_tool_calls(contents)

    assert len(partial.parts) == 1
    assert contents[1] is not partial


# --- Real ADK runs -----------------------------------------------------------


def test_factory_installs_the_repair_plugin_once() -> None:
    app = create_deep_agent(
        name="root",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        plugins=[ToolCallRepairPlugin()],
    )

    assert sum(isinstance(plugin, ToolCallRepairPlugin) for plugin in app.plugins) == 1
    assert isinstance(app.plugins[0], ToolCallRepairPlugin)


@pytest.mark.asyncio
async def test_call_left_by_a_crash_is_answered_and_history_is_unchanged() -> None:
    model = ScriptedModel(requests=[], responses=["recovered"])
    harness = Harness(create_deep_agent(name="root", model_client=model, instruction="Help."))
    session = await harness.session_service.create_session(app_name="root", user_id="test")
    harness.session_id = session.id
    await harness.session_service.append_event(
        session, Event(author="user", invocation_id="i1", content=_text("user", "do it"))
    )
    await harness.session_service.append_event(
        session,
        Event(
            author="root",
            invocation_id="i1",
            content=types.Content(role="model", parts=[_call_part("todo", "call-crashed")]),
        ),
    )

    await harness.turn("are you there?")

    request = model.requests[0]
    assert _unanswered_count(request) == 0
    assert [result.id for result in _interrupted_results(request)] == ["call-crashed"]
    stored = await harness.session_service.get_session(
        app_name="root", user_id="test", session_id=session.id
    )
    assert not any(event.get_function_responses() for event in stored.events)


@pytest.mark.asyncio
async def test_call_left_by_a_cancelled_run_is_answered() -> None:
    gate = asyncio.Event()

    async def slow(query: str) -> dict:
        """Slow lookup."""
        await gate.wait()
        return {}

    model = ScriptedModel(requests=[], responses=[_call("slow", {"query": "x"}), "recovered"])
    harness = Harness(
        create_deep_agent(name="root", model_client=model, instruction="Help.", tools=[slow])
    )

    turn = asyncio.create_task(harness.turn("start"))
    while not model.requests:
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn

    await harness.turn("are you there?")

    request = model.requests[1]
    assert _unanswered_count(request) == 0
    assert [result.name for result in _interrupted_results(request)] == ["slow"]


@pytest.mark.asyncio
async def test_plain_text_while_elicitation_is_pending_answers_the_request() -> None:
    model = ScriptedModel(
        requests=[],
        responses=[_call(REQUEST_INPUT_TOOL_NAME, {"message": "Which env?"}), "ok"],
    )
    harness = Harness(
        create_deep_agent(name="root", model_client=model, instruction="Help.", elicitation=True)
    )

    await harness.turn("deploy")
    await harness.turn("never mind, what is 2+2?")

    request = model.requests[1]
    assert _unanswered_count(request) == 0
    assert [result.name for result in _interrupted_results(request)] == [REQUEST_INPUT_TOOL_NAME]


@pytest.mark.asyncio
async def test_background_children_inherit_the_repair_plugin() -> None:
    child_model = ScriptedModel(requests=[], responses=["child done"])
    root_model = ScriptedModel(
        requests=[],
        responses=[
            _call(
                SPAWN_TOOL_NAME,
                {"name": "worker", "goal": "Work.", "model": "child", "background": True},
            ),
            "started",
        ],
    )
    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        available_models=[ModelSpec(id="child", model_client=child_model)],
        spawn=SpawnConfig(enabled=True),
    )
    harness = Harness(app)
    seen: list[Any] = []
    original = ToolCallRepairPlugin.before_model_callback

    async def spy(self, *, callback_context, llm_request):
        seen.append(callback_context.agent_name)
        return await original(self, callback_context=callback_context, llm_request=llm_request)

    ToolCallRepairPlugin.before_model_callback = spy
    try:
        events = await harness.turn("start")
        task_id = next(
            response.response["task_id"]
            for event in events
            for response in event.get_function_responses()
            if response.name == SPAWN_TOOL_NAME
        )
        await wait_for_background_task(task_id)
    finally:
        ToolCallRepairPlugin.before_model_callback = original

    assert "root" in seen
    assert "worker" in seen

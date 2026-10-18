from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from adk_agent_harness import REQUEST_INPUT_TOOL_NAME
from adk_agent_harness import create_deep_agent
from adk_agent_harness import create_elicitation_response
from adk_agent_harness import project_elicitation_event
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.events.event import Event
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types


class ElicitationModel(BaseLlm):
    model: str = "elicitation-model"
    responses: list[Any]
    requests: list[LlmRequest] = []

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        response = self.responses.pop(0)
        part = (
            types.Part.from_text(text=response)
            if isinstance(response, str)
            else response
        )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def _runner_for(app):
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=app.name, user_id="test")
    return (
        Runner(
            app=app,
            artifact_service=InMemoryArtifactService(),
            session_service=session_service,
            memory_service=InMemoryMemoryService(),
        ),
        session,
    )


@pytest.mark.asyncio
async def test_elicitation_interrupts_and_resumes_with_structured_answers() -> None:
    schema = {
        "type": "object",
        "properties": {
            "environment": {
                "type": "string",
                "enum": ["staging", "production"],
            }
        },
        "required": ["environment"],
    }
    model = ElicitationModel(
        responses=[
            types.Part.from_function_call(
                name=REQUEST_INPUT_TOOL_NAME,
                args={"message": "Choose an environment.", "response_schema": schema},
            ),
            "Continuing with production.",
        ]
    )
    app = create_deep_agent(
        name="eliciting_agent",
        model_client=model,
        instruction="Help.",
        elicitation=True,
    )
    runner, session = await _runner_for(app)

    interrupted_events = [
        event
        async for event in runner.run_async(
            user_id="test",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text="Deploy the app.")],
            ),
        )
    ]

    assert len(model.requests) == 1
    request = next(
        projected
        for event in interrupted_events
        if (projected := project_elicitation_event(event)) is not None
    )
    assert request.message == "Choose an environment."
    assert request.response_schema == schema
    assert request.id in {
        tool_id
        for event in interrupted_events
        for tool_id in (event.long_running_tool_ids or [])
    }

    resumed_events: list[Event] = []
    async for event in runner.run_async(
        user_id="test",
        session_id=session.id,
        invocation_id=request.invocation_id,
        new_message=create_elicitation_response(
            request,
            {"environment": "production"},
        ),
    ):
        resumed_events.append(event)

    assert len(model.requests) == 2
    assert any(
        part.text == "Continuing with production."
        for event in resumed_events
        for part in (event.content.parts if event.content else [])
    )


def test_elicitation_is_opt_in_and_enables_resumability() -> None:
    disabled = create_deep_agent(
        name="disabled",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
    )
    enabled = create_deep_agent(
        name="enabled",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        elicitation=True,
    )

    assert not any(
        getattr(tool, "name", "") == REQUEST_INPUT_TOOL_NAME
        for tool in disabled.root_agent.tools
    )
    assert any(
        getattr(tool, "name", "") == REQUEST_INPUT_TOOL_NAME
        for tool in enabled.root_agent.tools
    )
    assert enabled.resumability_config.is_resumable is True

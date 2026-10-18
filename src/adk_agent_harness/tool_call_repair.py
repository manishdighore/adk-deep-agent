"""Repair tool calls that never received a result before each model request.

A tool call can be left without a result when a run is cancelled or times out
mid-tool, the process crashes, or the user sends plain text while an
`adk_request_input` call is still waiting. ADK drops orphaned *results* but
still sends an unanswered *call* to the model, and OpenAI, Anthropic, and
Gemini all reject or misbehave on a call without a matching result.

`ToolCallRepairPlugin` runs before every model request of every agent in the
runner (root, prebuilt and spawned children, and background children, whose
runner inherits the parent's plugins). It inserts a synthetic error result
right after each unanswered call. Only the outgoing request is changed; the
session history is never mutated.

ADK strips its own `adk-` call IDs from request contents before callbacks run,
so a call is matched to its result by ID when both have one, and otherwise by
name within the result message that immediately follows the call, which is
the layout ADK's contents processor produces.
"""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

TOOL_CALL_REPAIR_PLUGIN_NAME = "adk_agent_harness_tool_call_repair"

INTERRUPTED_TOOL_RESULT = {
    "status": "interrupted",
    "error": (
        "This tool call did not complete because the run was interrupted "
        "before a result was recorded. Do not assume it succeeded; call the "
        "tool again if the result is still needed."
    ),
}


def _function_calls(content: types.Content) -> list[types.FunctionCall]:
    return [part.function_call for part in content.parts or [] if part.function_call]


def _function_responses(content: types.Content) -> list[types.FunctionResponse]:
    return [
        part.function_response
        for part in content.parts or []
        if part.function_response
    ]


def _unanswered_calls(
    calls: list[types.FunctionCall],
    responses: list[types.FunctionResponse],
    answered_ids: set[str],
) -> list[types.FunctionCall]:
    remaining = list(responses)
    unanswered: list[types.FunctionCall] = []
    for call in calls:
        if call.id and call.id in answered_ids:
            continue
        match = next(
            (
                response
                for response in remaining
                if (call.id and response.id == call.id)
                or (not response.id and response.name == call.name)
            ),
            None,
        )
        if match is None:
            unanswered.append(call)
        else:
            remaining.remove(match)
    return unanswered


def repair_dangling_tool_calls(contents: list[types.Content]) -> int:
    """Insert synthetic results for unanswered tool calls, in place.

    Returns the number of synthetic results inserted.
    """

    answered_ids = {
        response.id
        for content in contents
        for response in _function_responses(content)
        if response.id
    }
    repaired = 0
    index = 0
    while index < len(contents):
        calls = _function_calls(contents[index])
        if not calls:
            index += 1
            continue

        next_index = index + 1
        following = contents[next_index] if next_index < len(contents) else None
        following_responses = _function_responses(following) if following else []
        unanswered = _unanswered_calls(calls, following_responses, answered_ids)
        if unanswered:
            synthetic = [
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call.id,
                        name=call.name,
                        response=dict(INTERRUPTED_TOOL_RESULT),
                    )
                )
                for call in unanswered
            ]
            if following_responses:
                # Replace with a copy so a session-owned content is never mutated.
                contents[next_index] = following.model_copy(
                    update={"parts": [*(following.parts or []), *synthetic]}
                )
            else:
                contents.insert(next_index, types.Content(role="user", parts=synthetic))
            repaired += len(synthetic)
        index += 1
    return repaired


class ToolCallRepairPlugin(BasePlugin):
    """Answer dangling tool calls before every model request."""

    def __init__(self, name: str = TOOL_CALL_REPAIR_PLUGIN_NAME) -> None:
        super().__init__(name=name)

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        repair_dangling_tool_calls(llm_request.contents)
        return None

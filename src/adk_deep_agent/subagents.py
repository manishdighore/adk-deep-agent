"""Subagent helpers for adk-deep-agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.llm_agent import ToolUnion
from google.adk.models import BaseLlm
from google.adk.tools import FunctionTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .config import SpawnConfig
from .config import SubAgentSpec
from .models import ModelSpec

SPAWN_TOOL_NAME = "spawn_subagent"

SPAWN_TOOL_GUIDANCE = """You have a built-in `spawn_subagent` tool for focused delegated work.

Use it when a temporary specialist should handle a bounded task with explicit
goal, context, model, and allowed tools or skills. Select only a model from the
available model catalog. Spawned subagents are foreground workers: wait for
their result before finalizing your answer.
"""


def validate_agent_name(name: str) -> str:
    """Validate a name with ADK's agent-name rules."""

    stripped = name.strip()
    if not stripped.isidentifier() or stripped == "user":
        raise ValueError(
            "agent name must be a valid Python identifier and cannot be `user`"
        )
    return stripped


def _tool_name(tool: ToolUnion) -> str | None:
    if isinstance(tool, BaseTool):
        return tool.name
    if callable(tool):
        return getattr(tool, "__name__", None)
    return getattr(tool, "name", None)


def build_tool_registry(
    tools: Sequence[ToolUnion],
    extra_tools: Mapping[str, ToolUnion],
) -> dict[str, ToolUnion]:
    """Build a name-to-tool registry for spawned subagents."""

    registry: dict[str, ToolUnion] = {}
    for tool in tools:
        name = _tool_name(tool)
        if name:
            registry[name] = tool
    registry.update(extra_tools)
    return registry


def build_subagent_instruction(spec: SubAgentSpec) -> str:
    """Build an instruction for a prebuilt subagent."""

    if spec.instruction:
        return spec.instruction
    return (
        f"You are the `{spec.name}` subagent.\n\n"
        f"Goal: {spec.goal}\n\n"
        "Work independently on the assigned request. Return a concise result "
        "with key findings, decisions, and any blockers."
    )


def build_prebuilt_subagent(
    spec: SubAgentSpec,
    *,
    default_model_client: str | BaseLlm,
    planner_builder,
) -> Agent:
    """Create a prebuilt ADK child agent from a SubAgentSpec."""

    name = validate_agent_name(spec.name)
    child_tools: list[ToolUnion] = [*spec.tools]
    if spec.skills is not None:
        child_tools.append(spec.skills)

    return Agent(
        name=name,
        model=spec.model_client or default_model_client,
        instruction=build_subagent_instruction(spec),
        description=spec.description or spec.goal,
        tools=child_tools,
        planner=planner_builder(spec.thinking),
        mode=spec.mode,
    )


def _validate_selected_names(
    *,
    selected: Sequence[str] | None,
    registry: Mapping[str, Any],
    allowed: Sequence[str],
    kind: str,
) -> list[str]:
    names = [name.strip() for name in (selected or []) if name.strip()]
    allowed_set = set(allowed) if allowed else set(registry)
    unknown = [name for name in names if name not in registry]
    disallowed = [name for name in names if name not in allowed_set]
    if unknown:
        raise ValueError(f"unknown {kind}: {', '.join(sorted(unknown))}")
    if disallowed:
        raise ValueError(f"disallowed {kind}: {', '.join(sorted(disallowed))}")
    return names


def _build_spawn_instruction(
    *,
    name: str,
    goal: str,
    context: str | None,
) -> str:
    instruction = (
        f"You are the temporary `{name}` subagent.\n\n"
        f"Goal: {goal}\n\n"
        "Complete only this delegated task. Use the provided tools and skills "
        "when useful. Return a concise result for the parent agent."
    )
    if context:
        instruction += f"\n\nContext from parent:\n{context}"
    return instruction


def _last_text_from_child_events(events: Sequence[Any]) -> str | None:
    texts: list[str] = []
    for event in events:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None)
        if not parts:
            continue
        for part in parts:
            if isinstance(part, types.Part) and part.text and not part.thought:
                texts.append(part.text)
    return texts[-1] if texts else None


def create_spawn_subagent_tool(
    *,
    root_name: str,
    default_model_id: str,
    model_registry: Mapping[str, ModelSpec],
    config: SpawnConfig,
    tool_registry: Mapping[str, ToolUnion],
    skill_registry: Mapping[str, SkillToolset],
    reserved_names: set[str],
) -> FunctionTool:
    """Create the built-in on-demand spawn tool."""

    async def spawn_subagent(
        name: str,
        goal: str,
        context: str | None = None,
        tool_names: list[str] | None = None,
        skill_names: list[str] | None = None,
        mode: str | None = None,
        model: str | None = None,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Spawn a temporary ADK subagent for focused delegated work.

        Args:
            name: Temporary child agent name.
            goal: The delegated task goal.
            context: Optional parent context for the task.
            tool_names: Allowed tool names to provide to the child.
            skill_names: Allowed skill toolset names to provide to the child.
            mode: `single_turn` or `task`; defaults to package configuration.
            model: Allowed model ID; defaults to the root agent's model.
            tool_context: ADK tool context injected by the runtime.
        """

        if tool_context is None:
            return {
                "status": "error",
                "error": "spawn_subagent requires ToolContext",
            }

        try:
            child_name = validate_agent_name(name)
            if child_name in reserved_names or child_name == root_name:
                raise ValueError(f"agent name already reserved: {child_name}")

            selected_tools = _validate_selected_names(
                selected=tool_names,
                registry=tool_registry,
                allowed=config.allowed_tools,
                kind="tool(s)",
            )
            selected_skills = _validate_selected_names(
                selected=skill_names,
                registry=skill_registry,
                allowed=config.allowed_skills,
                kind="skill(s)",
            )

            child_mode = mode or config.default_mode
            if child_mode not in {"single_turn", "task"}:
                raise ValueError("mode must be `single_turn` or `task`")

            selected_model_id = (model or default_model_id).strip()
            if selected_model_id not in model_registry:
                raise ValueError(f"unknown model: {selected_model_id}")
            selected_model = model_registry[selected_model_id].model_client
            if selected_model is None:
                raise ValueError(f"model has no configured client: {selected_model_id}")

            child_tools: list[ToolUnion] = [
                tool_registry[name] for name in selected_tools
            ]
            child_tools.extend(skill_registry[name] for name in selected_skills)

            child = Agent(
                name=child_name,
                model=selected_model,
                instruction=_build_spawn_instruction(
                    name=child_name,
                    goal=goal,
                    context=context,
                ),
                description=goal,
                tools=child_tools,
                mode=child_mode,
            )
            event_start = len(tool_context.session.events)
            result = await tool_context.run_node(
                child,
                node_input=context or goal,
                use_sub_branch=True,
            )
            child_events = [
                event
                for event in tool_context.session.events[event_start:]
                if event.author == child_name
            ]
            if child_mode == "task" and result is None:
                return {
                    "status": "waiting_for_user",
                    "name": child_name,
                    "mode": child_mode,
                    "model": selected_model_id,
                    "message": _last_text_from_child_events(child_events),
                }
            return {
                "status": "completed",
                "name": child_name,
                "mode": child_mode,
                "model": selected_model_id,
                "result": result,
            }
        except Exception as exc:
            return {
                "status": "error",
                "name": name,
                "error": str(exc),
            }

    return FunctionTool(spawn_subagent)


def normalize_spawn_config(spawn: SpawnConfig | None) -> SpawnConfig | None:
    """Return enabled spawn config only."""

    if spawn is None or not spawn.enabled:
        return None
    return spawn

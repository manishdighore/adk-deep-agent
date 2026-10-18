"""Subagent helpers for adk-agent-harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.llm_agent import ToolUnion
from google.adk.events._branch_path import _BranchPath
from google.adk.models import BaseLlm
from google.adk.tools import FunctionTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.tool_context import ToolContext

from .background import start_background_child
from .config import SpawnConfig
from .config import SubAgentSpec
from .elicitation import REQUEST_INPUT_TOOL_NAME
from .models import ModelSpec
from .sandbox import SANDBOX_TOOLSET_NAME

SPAWN_TOOL_NAME = "spawn_subagent"
SPAWN_CHILD_MODE = "single_turn"

SPAWN_TOOL_GUIDANCE = """You have a built-in `spawn_subagent` tool for focused delegated work.

Use it when a temporary specialist should handle a bounded task with explicit
goal, context, model, and allowed tools or skills. Select only a model from the
available model catalog. Spawned subagents run once without user interaction,
so pass every detail they need in `goal` and `context`.

By default you wait for the subagent's result. Set `background=true` for
independent work you do not need before continuing: the call returns a task ID
immediately, and the result is reported to you automatically once the
subagent finishes. Background subagents do not see your session state.
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
    *,
    sandbox_toolset: ToolUnion | None = None,
) -> dict[str, ToolUnion]:
    """Build a name-to-tool registry for spawned subagents.

    A configured sandbox is registered under `SANDBOX_TOOLSET_NAME` so a spawned
    child can be granted the same workspace through `allowed_tools`.
    """

    registry: dict[str, ToolUnion] = {}
    for tool in tools:
        name = _tool_name(tool)
        if name:
            registry[name] = tool
    registry.update(extra_tools)
    if sandbox_toolset is not None:
        registry.setdefault(SANDBOX_TOOLSET_NAME, sandbox_toolset)
    # Spawned children run in single-turn mode and never talk to the user.
    for name, tool in list(registry.items()):
        if REQUEST_INPUT_TOOL_NAME in {name, _tool_name(tool)}:
            del registry[name]
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
    sandbox_toolset: ToolUnion | None = None,
    sandbox_code_executor: Any | None = None,
) -> Agent:
    """Create a prebuilt ADK child agent from a SubAgentSpec."""

    name = validate_agent_name(spec.name)
    child_tools: list[ToolUnion] = [*spec.tools]
    if spec.skills is not None:
        child_tools.append(spec.skills)
    if spec.use_sandbox and sandbox_toolset is not None:
        child_tools.append(sandbox_toolset)

    return Agent(
        name=name,
        model=spec.model_client or default_model_client,
        instruction=build_subagent_instruction(spec),
        description=spec.description or spec.goal,
        tools=child_tools,
        planner=planner_builder(spec.thinking),
        code_executor=sandbox_code_executor if spec.use_sandbox else None,
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


def _build_spawn_instruction(name: str) -> str:
    return (
        f"You are the temporary `{name}` subagent.\n\n"
        "Complete only the delegated task in the request. Use the provided "
        "tools and skills when useful. You cannot ask the user questions; "
        "state any assumptions you make. Return a concise result for the "
        "parent agent."
    )


def _build_spawn_request(goal: str, context: str | None) -> str:
    request = f"Goal: {goal}"
    if context:
        request += f"\n\nContext from parent:\n{context}"
    return request


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
        model: str | None = None,
        background: bool = False,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Spawn a temporary ADK subagent for focused delegated work.

        Args:
            name: Temporary child agent name.
            goal: The delegated task goal.
            context: Optional parent context for the task.
            tool_names: Allowed tool names to provide to the child.
            skill_names: Allowed skill toolset names to provide to the child.
            model: Allowed model ID; defaults to the root agent's model.
            background: Run the child in the background and return a task ID
                immediately. Its result is reported to you when it finishes.
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
                instruction=_build_spawn_instruction(child_name),
                description=goal,
                tools=child_tools,
                # ADK rejects `single_turn` for a Runner root agent, so a
                # background child keeps the default mode, as with AgentTool.
                # It still receives one request and cannot reach the user.
                mode=None if background else SPAWN_CHILD_MODE,
            )

            request = _build_spawn_request(goal, context)
            if background:
                task = await start_background_child(
                    child,
                    request=request,
                    goal=goal,
                    model_id=selected_model_id,
                    tool_context=tool_context,
                )
                return {
                    "status": "running",
                    "task_id": task.task_id,
                    "name": child_name,
                    "model": selected_model_id,
                }

            # Mirror ADK's `_SingleTurnAgentTool`: run the child on a sub-branch
            # keyed by this function call so its events correlate to the call.
            child_branch = _BranchPath.create_sub_branch(
                tool_context.get_invocation_context().branch,
                name=child_name,
                run_id=tool_context.function_call_id,
            )
            result = await tool_context.run_node(
                child,
                node_input=request,
                override_branch=child_branch,
                use_sub_branch=False,
            )
            return {
                "status": "completed",
                "name": child_name,
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

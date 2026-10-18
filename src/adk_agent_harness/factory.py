"""Factory for building ADK deep agents."""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents import Agent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.llm_agent import ToolUnion
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.app import ResumabilityConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.environment import BaseEnvironment
from google.adk.models import BaseLlm
from google.adk.planners import BuiltInPlanner
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import request_input
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from .background import inject_background_task_updates
from .callbacks import guard_multiple_todo_writes
from .callbacks import inject_active_ledger
from .config import CompactionConfig
from .config import SpawnConfig
from .config import SubAgentSpec
from .config import ThinkingConfig
from .elicitation import ELICITATION_TOOL_GUIDANCE
from .models import ModelSpec
from .models import build_model_registry
from .models import format_model_catalog
from .sandbox import SandboxConfig
from .sandbox import SandboxKind
from .sandbox import build_sandbox
from .subagents import SPAWN_TOOL_GUIDANCE
from .subagents import build_prebuilt_subagent
from .subagents import build_tool_registry
from .subagents import create_spawn_subagent_tool
from .subagents import normalize_spawn_config
from .subagents import validate_agent_name
from .tool import create_todo_tool
from .tool_call_repair import ToolCallRepairPlugin

LEDGER_TOOL_GUIDANCE = """You have a built-in `todo` tool for tracking multi-step work.

Use it for complex tasks that need planning or progress tracking. Keep exactly
one item in progress when possible, mark completed work promptly, and keep the
ledger current before returning a final answer.
"""

COMPACTION_PROMPT_TEMPLATE = """Summarize this conversation history for a long-running deep agent.

Capture:
1. User goal and constraints.
2. Completed actions and results.
3. Changed files, resources, or generated outputs.
4. Outstanding issues.
5. Next intended action.

Do not treat this summary as the source of truth for the task ledger. Current
todo state is stored separately in ADK session state.

Conversation history:
{conversation_history}
"""


def _build_instruction(
    instruction: str,
    *,
    include_spawn_guidance: bool = False,
    include_elicitation_guidance: bool = False,
    model_catalog: str | None = None,
) -> str:
    guidance = [LEDGER_TOOL_GUIDANCE.strip()]
    if include_spawn_guidance:
        guidance.append(SPAWN_TOOL_GUIDANCE.strip())
    if include_elicitation_guidance:
        guidance.append(ELICITATION_TOOL_GUIDANCE.strip())
    if model_catalog:
        guidance.append(model_catalog.strip())
    return f"{instruction.rstrip()}\n\n" + "\n\n".join(guidance)


def _build_planner(thinking: bool | ThinkingConfig):
    if thinking is False:
        return None
    if thinking is True:
        config = types.ThinkingConfig()
    elif thinking.enabled:
        config = types.ThinkingConfig(
            include_thoughts=thinking.include_thoughts,
            thinking_budget=thinking.thinking_budget,
        )
    else:
        return None
    return BuiltInPlanner(thinking_config=config)


def _build_context_cache_config(
    context_cache: bool | ContextCacheConfig | None,
) -> ContextCacheConfig | None:
    if context_cache is None or context_cache is False:
        return None
    if context_cache is True:
        return ContextCacheConfig()
    return context_cache


def _build_compaction_config(
    compaction: CompactionConfig | None,
    root_agent: Agent,
) -> EventsCompactionConfig | None:
    if compaction is None:
        return None

    summarizer = LlmEventSummarizer(
        llm=root_agent.canonical_model,
        prompt_template=COMPACTION_PROMPT_TEMPLATE,
    )
    return EventsCompactionConfig(
        summarizer=summarizer,
        compaction_interval=compaction.compaction_interval,
        overlap_size=compaction.overlap_size,
        token_threshold=compaction.token_threshold,
        event_retention_size=compaction.event_retention_size,
    )


def create_deep_agent(
    *,
    name: str,
    model_client: str | BaseLlm,
    instruction: str,
    description: str = "",
    tools: Sequence[ToolUnion] = (),
    skills: SkillToolset | None = None,
    thinking: bool | ThinkingConfig = False,
    compaction: CompactionConfig | None = None,
    plugins: Sequence[BasePlugin] = (),
    subagents: Sequence[SubAgentSpec] = (),
    spawn: SpawnConfig | None = None,
    elicitation: bool = False,
    available_models: Sequence[str | ModelSpec] = (),
    sandbox: SandboxKind | SandboxConfig | BaseEnvironment | None = None,
    context_cache: bool | ContextCacheConfig | None = None,
) -> App:
    """Create a standard ADK `App` with deep-agent behavior pre-wired.

    The returned `App` always includes the built-in `todo` task ledger, active
    ledger injection before each root model request, and `ToolCallRepairPlugin`.
    Everything else is opt-in. Run the `App` with any ADK `Runner` and the
    session, artifact, and memory services your application chooses.

    Args:
        name: Root agent and App name. Must be a valid Python identifier and
            cannot be `user`.
        model_client: Root model. A model name string or any ADK `BaseLlm`,
            such as `LiteLlm`.
        instruction: Root agent instruction. Package guidance for the enabled
            features is appended to it.
        description: Optional root agent description.
        tools: Tools for the root agent: functions, ADK `BaseTool` or
            `BaseToolset` values, including MCP toolsets.
        skills: One ADK `SkillToolset` for the root agent.
        thinking: `True`, `False`, or a `ThinkingConfig`; mapped to ADK's
            `BuiltInPlanner`.
        compaction: Optional `CompactionConfig` enabling ADK event compaction
            with a summary prompt written for long-running work.
        plugins: Additional ADK plugins for the App. `ToolCallRepairPlugin` is
            always installed first.
        subagents: Prebuilt children declared with `SubAgentSpec`, attached as
            native ADK `sub_agents`.
        spawn: `SpawnConfig(enabled=True, ...)` adds the `spawn_subagent` tool so
            the root agent can create temporary children at runtime, in the
            foreground or in the background.
        elicitation: Add ADK's `request_input` tool to the root agent and make
            the App resumable, for structured questions to the user.
        available_models: Models a spawned child may select, as IDs or
            `ModelSpec` values. The root model is always included as the
            default. Only IDs and descriptions reach the model.
        sandbox: Optional workspace for shell and file tools. Accepts a backend
            name (`local`, `daytona`, `e2b`, `cloud_run`), a `SandboxConfig`, or
            a preconstructed ADK `BaseEnvironment`. Filesystem backends attach
            ADK's `EnvironmentToolset`; `cloud_run` attaches ADK's Cloud Run
            sandbox code executor instead. Credentials are preflighted here.
            One environment is created per App and shared by all its sessions.
        context_cache: Optional ADK context caching. `True` uses ADK defaults;
            pass an ADK `ContextCacheConfig` to tune intervals and TTL.

    Returns:
        A standard `google.adk.apps.App`.

    Raises:
        ValueError: For invalid or duplicate agent names, or a subagent that
            requests a sandbox when none is configured.
        SandboxConfigurationError: When a selected sandbox backend is missing
            credentials or packages.
    """

    root_tools: list[ToolUnion] = [*tools]
    if skills is not None:
        root_tools.append(skills)

    attached_sandbox = build_sandbox(sandbox)
    if attached_sandbox.toolset is not None:
        root_tools.append(attached_sandbox.toolset)

    spawn_config = normalize_spawn_config(spawn)
    default_model_id, model_registry = build_model_registry(
        default_model_client=model_client,
        available_models=available_models,
    )
    if attached_sandbox.toolset is None and attached_sandbox.code_executor is None:
        sandbox_children = [spec.name for spec in subagents if spec.use_sandbox]
        if sandbox_children:
            joined = ", ".join(sandbox_children)
            raise ValueError(
                f"subagent(s) request a sandbox but none is configured: {joined}"
            )

    child_agents = [
        build_prebuilt_subagent(
            spec,
            default_model_client=model_client,
            planner_builder=_build_planner,
            sandbox_toolset=attached_sandbox.toolset,
            sandbox_code_executor=attached_sandbox.code_executor,
        )
        for spec in subagents
    ]
    reserved_names = {name, *(child.name for child in child_agents)}

    if len(reserved_names) != len(child_agents) + 1:
        raise ValueError("root and subagent names must be unique")

    validate_agent_name(name)
    if spawn_config is not None:
        tool_registry = build_tool_registry(
            tools,
            spawn_config.tools,
            sandbox_toolset=attached_sandbox.toolset,
        )
        root_tools.append(
            create_spawn_subagent_tool(
                root_name=name,
                default_model_id=default_model_id,
                model_registry=model_registry,
                config=spawn_config,
                tool_registry=tool_registry,
                skill_registry=spawn_config.skills,
                reserved_names=reserved_names,
            )
        )

    if elicitation:
        root_tools.append(request_input)

    root_tools.append(create_todo_tool())

    root_agent = Agent(
        name=name,
        model=model_client,
        instruction=_build_instruction(
            instruction,
            include_spawn_guidance=spawn_config is not None,
            include_elicitation_guidance=elicitation,
            model_catalog=(
                format_model_catalog(
                    model_registry,
                    default_model_id=default_model_id,
                )
                if spawn_config is not None
                else None
            ),
        ),
        description=description,
        tools=root_tools,
        sub_agents=child_agents,
        planner=_build_planner(thinking),
        code_executor=attached_sandbox.code_executor,
        before_model_callback=(
            [inject_active_ledger, inject_background_task_updates]
            if spawn_config is not None
            else inject_active_ledger
        ),
        after_model_callback=guard_multiple_todo_writes,
    )

    return App(
        name=name,
        root_agent=root_agent,
        plugins=[
            ToolCallRepairPlugin(),
            *(plugin for plugin in plugins if not isinstance(plugin, ToolCallRepairPlugin)),
        ],
        resumability_config=(
            ResumabilityConfig(is_resumable=True) if elicitation else None
        ),
        events_compaction_config=_build_compaction_config(compaction, root_agent),
        context_cache_config=_build_context_cache_config(context_cache),
    )

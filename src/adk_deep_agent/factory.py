"""Factory for building ADK deep agents."""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents import Agent
from google.adk.agents.llm_agent import ToolUnion
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import BaseLlm
from google.adk.planners import BuiltInPlanner
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from .callbacks import guard_multiple_todo_writes
from .callbacks import inject_active_ledger
from .config import CompactionConfig
from .config import SpawnConfig
from .config import SubAgentSpec
from .config import ThinkingConfig
from .subagents import SPAWN_TOOL_GUIDANCE
from .subagents import build_prebuilt_subagent
from .subagents import build_tool_registry
from .subagents import create_spawn_subagent_tool
from .subagents import normalize_spawn_config
from .subagents import validate_agent_name
from .tool import create_todo_tool

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
) -> str:
    guidance = [LEDGER_TOOL_GUIDANCE.strip()]
    if include_spawn_guidance:
        guidance.append(SPAWN_TOOL_GUIDANCE.strip())
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
) -> App:
    """Create a standard ADK App with deep-agent behavior."""

    root_tools: list[ToolUnion] = [*tools]
    if skills is not None:
        root_tools.append(skills)

    spawn_config = normalize_spawn_config(spawn)
    child_agents = [
        build_prebuilt_subagent(
            spec,
            default_model_client=model_client,
            planner_builder=_build_planner,
        )
        for spec in subagents
    ]
    reserved_names = {name, *(child.name for child in child_agents)}

    if len(reserved_names) != len(child_agents) + 1:
        raise ValueError("root and subagent names must be unique")

    validate_agent_name(name)
    if spawn_config is not None:
        tool_registry = build_tool_registry(tools, spawn_config.tools)
        root_tools.append(
            create_spawn_subagent_tool(
                root_name=name,
                model_client=model_client,
                config=spawn_config,
                tool_registry=tool_registry,
                skill_registry=spawn_config.skills,
                reserved_names=reserved_names,
            )
        )

    root_tools.append(create_todo_tool())

    root_agent = Agent(
        name=name,
        model=model_client,
        instruction=_build_instruction(
            instruction,
            include_spawn_guidance=spawn_config is not None,
        ),
        description=description,
        tools=root_tools,
        sub_agents=child_agents,
        planner=_build_planner(thinking),
        before_model_callback=inject_active_ledger,
        after_model_callback=guard_multiple_todo_writes,
    )

    return App(
        name=name,
        root_agent=root_agent,
        plugins=list(plugins),
        events_compaction_config=_build_compaction_config(compaction, root_agent),
    )

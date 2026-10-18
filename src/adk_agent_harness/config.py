"""Configuration models for adk-agent-harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from google.adk.agents.llm_agent import ToolUnion
from google.adk.models import BaseLlm
from google.adk.tools.skill_toolset import SkillToolset
from pydantic import BaseModel, ConfigDict, Field


class ThinkingConfig(BaseModel):
    """Model thinking settings, mapped to ADK's `BuiltInPlanner`."""

    enabled: bool = True
    """Turn thinking on. `False` attaches no planner."""

    include_thoughts: bool = False
    """Ask the model to return thought summaries, so a UI can show reasoning."""

    thinking_budget: int | None = None
    """Maximum thinking tokens. `None` uses the model default."""


class CompactionConfig(BaseModel):
    """ADK event compaction settings.

    When the latest prompt exceeds `token_threshold`, older events are
    summarized with a prompt written for long-running work. The task ledger is
    stored separately in session state and is never lost to compaction.
    """

    token_threshold: int = Field(gt=0)
    """Prompt token count that triggers compaction."""

    event_retention_size: int = Field(default=20, ge=0)
    """Number of most recent events kept verbatim after compaction."""

    compaction_interval: int = Field(default=999, gt=0)
    """ADK's invocation-count trigger. The high default leaves compaction
    driven by `token_threshold`."""

    overlap_size: int = Field(default=0, ge=0)
    """Events shared between consecutive compaction windows."""


SubAgentMode = Literal["single_turn", "task"]
"""`single_turn` runs once without user interaction; `task` may ask the user
for input until it calls ADK's `finish_task`."""


class SubAgentSpec(BaseModel):
    """A prebuilt subagent, attached as a native ADK `sub_agent`.

    ADK exposes it to the root agent as a tool named after the subagent, runs
    it on its own branch of the root session, and streams its events in the
    root `run_async()` stream.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """Child name and tool name. A valid Python identifier, unique in the App."""

    goal: str
    """What the child does. Used for its default instruction and description."""

    instruction: str | None = None
    """Full instruction. Overrides the instruction generated from `goal`."""

    description: str = ""
    """Tool description shown to the root agent. Defaults to `goal`."""

    model_client: str | BaseLlm | None = None
    """Model for this child. Defaults to the root model."""

    tools: Sequence[ToolUnion] = ()
    """Tools for this child only."""

    skills: SkillToolset | None = None
    """One ADK `SkillToolset` for this child."""

    mode: SubAgentMode = "single_turn"
    """ADK subagent mode."""

    thinking: bool | ThinkingConfig = False
    """Thinking settings for this child."""

    use_sandbox: bool = False
    """Grant this child the root agent's configured sandbox workspace."""


class SpawnConfig(BaseModel):
    """On-demand spawned subagent configuration.

    Enabling it adds the `spawn_subagent` tool. Spawned children always run in
    ADK `single_turn` mode: they complete the delegated request once, without
    user interaction, and return a result. The root agent chooses per call
    whether to wait (the default) or run the child in the background.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = False
    """Add the `spawn_subagent` tool to the root agent."""

    tools: Mapping[str, ToolUnion] = Field(default_factory=dict)
    """Extra tools spawned children may use, by name. The root agent's own
    tools and the sandbox (`environment`) are offered too."""

    skills: Mapping[str, SkillToolset] = Field(default_factory=dict)
    """Skill toolsets spawned children may use, by name."""

    allowed_tools: Sequence[str] = ()
    """Tool names a child may select. Empty allows every registered tool."""

    allowed_skills: Sequence[str] = ()
    """Skill names a child may select. Empty allows every registered skill."""

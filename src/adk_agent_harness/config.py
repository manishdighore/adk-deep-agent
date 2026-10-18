"""Configuration models for adk-agent-harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from google.adk.agents.llm_agent import ToolUnion
from google.adk.models import BaseLlm
from google.adk.tools.skill_toolset import SkillToolset
from pydantic import BaseModel, ConfigDict, Field


class ThinkingConfig(BaseModel):
    """Wrapper-managed model thinking configuration."""

    enabled: bool = True
    include_thoughts: bool = False
    thinking_budget: int | None = None


class CompactionConfig(BaseModel):
    """Simplified native ADK event compaction configuration."""

    token_threshold: int = Field(gt=0)
    event_retention_size: int = Field(default=20, ge=0)
    compaction_interval: int = Field(default=999, gt=0)
    overlap_size: int = Field(default=0, ge=0)


SubAgentMode = Literal["single_turn", "task"]


class SubAgentSpec(BaseModel):
    """Developer-declared prebuilt subagent configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    goal: str
    instruction: str | None = None
    description: str = ""
    model_client: str | BaseLlm | None = None
    tools: Sequence[ToolUnion] = ()
    skills: SkillToolset | None = None
    mode: SubAgentMode = "single_turn"
    thinking: bool | ThinkingConfig = False
    use_sandbox: bool = False
    """Grant this child the root agent's configured sandbox workspace."""


class SpawnConfig(BaseModel):
    """On-demand spawned subagent configuration.

    Spawned children always run in ADK `single_turn` mode: they complete the
    delegated request once, without user interaction, and return a result.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = False
    tools: Mapping[str, ToolUnion] = Field(default_factory=dict)
    skills: Mapping[str, SkillToolset] = Field(default_factory=dict)
    allowed_tools: Sequence[str] = ()
    allowed_skills: Sequence[str] = ()

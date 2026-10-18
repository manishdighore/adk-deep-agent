from collections.abc import AsyncGenerator

from adk_agent_harness import CompactionConfig
from adk_agent_harness import ThinkingConfig
from adk_agent_harness import create_deep_agent
from adk_agent_harness.ledger import TODO_TOOL_NAME
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.planners import BuiltInPlanner


class FakeLlm(BaseLlm):
    model: str = "fake-model"

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        yield LlmResponse()


def sample_tool(query: str) -> str:
    """Sample callable tool."""

    return query


def test_factory_returns_app_with_root_agent_and_todo_tool() -> None:
    app = create_deep_agent(
        name="test_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        tools=[sample_tool],
    )

    assert app.name == "test_agent"
    assert app.root_agent.model == "gemini-3-flash-preview"
    assert app.root_agent.planner is None
    assert sample_tool in app.root_agent.tools
    assert any(getattr(tool, "name", "") == TODO_TOOL_NAME for tool in app.root_agent.tools)


def test_factory_passes_thinking_config_to_built_in_planner() -> None:
    app = create_deep_agent(
        name="thinking_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        thinking=ThinkingConfig(include_thoughts=True, thinking_budget=1024),
    )

    assert isinstance(app.root_agent.planner, BuiltInPlanner)
    assert app.root_agent.planner.thinking_config.include_thoughts is True
    assert app.root_agent.planner.thinking_config.thinking_budget == 1024


def test_factory_supports_boolean_thinking() -> None:
    app = create_deep_agent(
        name="thinking_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        thinking=True,
    )

    assert isinstance(app.root_agent.planner, BuiltInPlanner)


def test_factory_maps_compaction_config() -> None:
    app = create_deep_agent(
        name="compact_agent",
        model_client=FakeLlm(),
        instruction="Help.",
        compaction=CompactionConfig(
            token_threshold=1000,
            event_retention_size=10,
            compaction_interval=999,
            overlap_size=0,
        ),
    )

    config = app.events_compaction_config
    assert config is not None
    assert config.token_threshold == 1000
    assert config.event_retention_size == 10
    assert config.compaction_interval == 999
    assert config.overlap_size == 0
    assert config.summarizer is not None



def test_factory_enables_context_cache_with_adk_defaults() -> None:
    app = create_deep_agent(
        name="cached_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        context_cache=True,
    )

    assert isinstance(app.context_cache_config, ContextCacheConfig)
    assert app.context_cache_config.cache_intervals == ContextCacheConfig().cache_intervals


def test_factory_passes_through_context_cache_config() -> None:
    config = ContextCacheConfig(cache_intervals=3, ttl_seconds=600, min_tokens=2048)

    app = create_deep_agent(
        name="cached_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        context_cache=config,
    )

    assert app.context_cache_config is config


def test_factory_leaves_context_cache_disabled_by_default() -> None:
    app = create_deep_agent(
        name="uncached_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
    )

    assert app.context_cache_config is None

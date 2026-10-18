"""04: Configure prebuilt and on-demand subagents."""

from adk_agent_harness import SpawnConfig
from adk_agent_harness import SubAgentSpec
from adk_agent_harness import create_deep_agent


def search_docs(query: str) -> str:
    """Search project documentation."""

    return f"No documentation backend configured for: {query}"


def inspect_code(path: str) -> str:
    """Inspect a code path."""

    return f"No code inspection backend configured for: {path}"


app = create_deep_agent(
    name="subagent_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction=(
        "Solve complex engineering tasks. Use prebuilt specialists or spawn "
        "temporary specialists when focused delegated work would help."
    ),
    tools=[search_docs],
    subagents=[
        SubAgentSpec(
            name="reviewer",
            goal="Review implementation plans and code changes for risks.",
            tools=[inspect_code],
            mode="single_turn",
        ),
        SubAgentSpec(
            name="clarifier",
            goal="Resolve unclear task requirements with the user.",
            mode="task",
        ),
    ],
    spawn=SpawnConfig(
        enabled=True,
        tools={
            "search_docs": search_docs,
            "inspect_code": inspect_code,
        },
        allowed_tools=["search_docs", "inspect_code"],
    ),
)


if __name__ == "__main__":
    print(app)

"""01: Create a basic ADK Agent Harness with the built-in todo ledger."""

from adk_agent_harness import create_deep_agent


def search_notes(query: str) -> str:
    """Search local notes for a query."""

    return f"No local note search backend configured for: {query}"


app = create_deep_agent(
    name="basic_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction="Help the user solve multi-step tasks accurately.",
    tools=[search_notes],
)


if __name__ == "__main__":
    print(app)


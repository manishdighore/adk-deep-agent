"""05: Enable structured elicitation and model-aware spawned agents."""

from adk_deep_agent import ModelSpec
from adk_deep_agent import SpawnConfig
from adk_deep_agent import create_deep_agent


app = create_deep_agent(
    name="interactive_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction=(
        "Resolve complex tasks. Ask for missing required decisions and choose "
        "an appropriate model when spawning focused specialists."
    ),
    elicitation=True,
    available_models=[
        ModelSpec(
            id="fast",
            model_client="gemini-3-flash-preview",
            description="Fast general-purpose delegated work.",
        ),
        ModelSpec(
            id="strong",
            model_client="gemini-3-pro-preview",
            description="Difficult reasoning and review work.",
            capabilities=["reasoning", "review"],
        ),
    ],
    spawn=SpawnConfig(enabled=True),
)


if __name__ == "__main__":
    print(app)

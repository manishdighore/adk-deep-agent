"""03: Enable thinking, native ADK event compaction, and plugins."""

from adk_deep_agent import CompactionConfig
from adk_deep_agent import ThinkingConfig
from adk_deep_agent import create_deep_agent
from google.adk.plugins.base_plugin import BasePlugin


class AuditPlugin(BasePlugin):
    """Tiny placeholder plugin for app-wide audit behavior."""

    def __init__(self) -> None:
        super().__init__(name="audit")


app = create_deep_agent(
    name="configured_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction="Work carefully and keep the task ledger current.",
    thinking=ThinkingConfig(
        enabled=True,
        include_thoughts=True,
        thinking_budget=1024,
    ),
    compaction=CompactionConfig(token_threshold=48000),
    plugins=[AuditPlugin()],
)


if __name__ == "__main__":
    print(app)


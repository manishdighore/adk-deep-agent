"""Public API for adk-deep-agent."""

from .config import CompactionConfig
from .config import SpawnConfig
from .config import SubAgentMode
from .config import SubAgentSpec
from .config import ThinkingConfig
from .events import SubagentEvent
from .events import iter_subagent_events
from .events import project_subagent_event
from .factory import create_deep_agent
from .ledger import (
    LEDGER_STATE_KEY,
    TaskLedgerItem,
    TaskLedgerResult,
    TaskLedgerStatus,
    TaskLedgerSummary,
)

__version__ = "0.1.0"

__all__ = [
    "CompactionConfig",
    "LEDGER_STATE_KEY",
    "SpawnConfig",
    "SubAgentMode",
    "SubAgentSpec",
    "SubagentEvent",
    "TaskLedgerItem",
    "TaskLedgerResult",
    "TaskLedgerStatus",
    "TaskLedgerSummary",
    "ThinkingConfig",
    "__version__",
    "create_deep_agent",
    "iter_subagent_events",
    "project_subagent_event",
]

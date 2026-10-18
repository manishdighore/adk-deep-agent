"""06: Attach a sandbox workspace and enable ADK context caching.

Sandbox backends and their required environment variables:

- `local`     no credentials; runs local subprocesses with no isolation
- `daytona`   DAYTONA_API_KEY (optional: DAYTONA_API_URL, DAYTONA_TARGET),
              `pip install "google-adk[daytona]"`
- `e2b`       E2B_API_KEY (optional: E2B_DOMAIN),
              `pip install "google-adk[e2b]"`
- `cloud_run` no credentials; code execution only, and only from inside a
              Cloud Run container deployed with `--sandbox-launcher`

Print the full table at any time with `sandbox_requirements_report()`.
"""

import os

from adk_agent_harness import SandboxConfig
from adk_agent_harness import SpawnConfig
from adk_agent_harness import SubAgentSpec
from adk_agent_harness import create_deep_agent
from adk_agent_harness import missing_sandbox_requirements
from adk_agent_harness import sandbox_requirements_report
from adk_agent_harness.sandbox import SANDBOX_TOOLSET_NAME
from google.adk.agents.context_cache_config import ContextCacheConfig

# Pick a remote sandbox when its credentials are present, otherwise stay local.
remote = SandboxConfig(kind="e2b", timeout=600)
sandbox = remote if not missing_sandbox_requirements(remote) else SandboxConfig(
    kind="local",
    working_dir=os.environ.get("DEEP_AGENT_WORKSPACE"),
    max_output_chars=30_000,
)

app = create_deep_agent(
    name="sandboxed_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction=(
        "Work inside the provided workspace. Read files before editing them, "
        "and keep the task ledger current."
    ),
    sandbox=sandbox,
    # Cache the stable instruction prefix across turns of a long session.
    context_cache=ContextCacheConfig(
        cache_intervals=5,
        ttl_seconds=900,
        min_tokens=2048,
    ),
    subagents=[
        # Shares the root workspace: same files, same shell.
        SubAgentSpec(name="builder", goal="Implement changes.", use_sandbox=True),
        # No workspace access.
        SubAgentSpec(name="planner", goal="Draft an implementation plan."),
    ],
    spawn=SpawnConfig(
        enabled=True,
        # Spawned children may request the workspace by this name.
        allowed_tools=[SANDBOX_TOOLSET_NAME],
    ),
)


if __name__ == "__main__":
    print(sandbox_requirements_report())
    print()
    print(app)

# ADK Agent Harness

`adk-agent-harness` turns a Google ADK agent into a **deep agent**: one that
plans, delegates to subagents, works in the background, asks the user for
structured input, and keeps long sessions on track.

It doesn't replace ADK. One factory, `create_deep_agent(...)`, returns a
standard `google.adk.apps.App`. You run it with an ordinary ADK `Runner`,
your own model client, and your own session service. Every event your UI
receives is a normal ADK event.

```python
from adk_agent_harness import SpawnConfig, create_deep_agent

app = create_deep_agent(
    name="research_assistant",
    model_client="gemini-3-flash-preview",
    instruction="Research thoroughly and keep your plan current.",
    spawn=SpawnConfig(enabled=True),
    elicitation=True,
)
```

## What it adds to ADK

| Feature | What you get | Built on (ADK) |
| --- | --- | --- |
| [Task ledger](guides/task-ledger.md) | A `todo` tool for plans and progress, stored in session state and shown to the model before every call | Session state, model callbacks |
| [Prebuilt subagents](guides/subagents.md) | `SubAgentSpec`: declare children with their own model, tools, skills, thinking, and sandbox access | `sub_agents`, `single_turn` / `task` modes |
| [Spawned subagents](guides/subagents.md#spawned-subagents) | A `spawn_subagent` tool: the agent creates a focused child at runtime from tools, skills, and models you allow | `ToolContext.run_node`, the same path as ADK's single-turn subagents |
| [Background subagents](guides/background-subagents.md) | `spawn_subagent(..., background=true)`: the child runs in isolation while the root agent continues, and the result is reported back automatically | A separate `Runner`, as in ADK's `AgentTool` |
| [Model selection](guides/models.md) | A model catalog the agent can choose from for children, validated against one registry | — |
| [Asking the user](guides/elicitation.md) | Structured questions with a JSON schema, pause and resume, and helpers for your UI | `request_input`, resumable `App` |
| [Sandbox workspaces](guides/sandbox.md) | `sandbox=` set to `"local"`, `"daytona"`, `"e2b"`, or `"cloud_run"`, with credential checks at build time and a workspace shared with subagents | `EnvironmentToolset`, ADK environments |
| [Interrupted tool calls](guides/tool-call-repair.md) | Tool calls left without a result (cancel, crash, ignored form) are answered before the next model call, so providers don't reject the session | Plugins |
| [Thinking, compaction, caching](guides/context.md) | One-line settings, plus a compaction prompt written for long-running work | `BuiltInPlanner`, event compaction, context cache |

Everything not in this table is plain ADK. Sessions, streaming, artifacts,
memory, tools, MCP, and skills all work exactly as ADK documents them.

## Install

```bash
pip install adk-agent-harness
```

Python 3.10+ and `google-adk>=2.7.1,<3`. See
[Getting started](getting-started.md) for optional extras and a first run.

## Design principles

- **ADK-native.** The package composes ADK primitives instead of wrapping
  them. If ADK provides something, the package uses it.
- **Your infrastructure.** Model clients, session services, and credentials
  are yours. Nothing in the package picks a provider or a database for you.
- **Explicit capabilities.** The model only sees the tools, skills, and models
  you allow. Credentials and model clients never enter model context.

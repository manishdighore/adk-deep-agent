<p align="center">
  <img src="https://raw.githubusercontent.com/manishdighore/adk-deep-agent/main/docs/assets/icon.svg" alt="adk-agent-harness" width="112" height="112">
</p>

<h3 align="center">adk-agent-harness</h3>

<p align="center">
  Deep-agent ergonomics on top of native Google ADK primitives.
</p>

<p align="center">
  <a href="https://pypi.org/project/adk-agent-harness/"><img alt="PyPI" src="https://img.shields.io/pypi/v/adk-agent-harness.svg"></a>
  <a href="https://pypi.org/project/adk-agent-harness/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/adk-agent-harness.svg"></a>
  <a href="https://github.com/manishdighore/adk-deep-agent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/manishdighore/adk-deep-agent/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/manishdighore/adk-deep-agent/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://github.com/google/adk-python"><img alt="Google ADK" src="https://img.shields.io/badge/Google%20ADK-2.7%2B-4285F4.svg"></a>
</p>

`adk-agent-harness` is a small Python package that creates a standard
`google.adk.apps.App` with deep-agent capabilities pre-wired: a task ledger,
context injection, structured user elicitation, thinking, compaction, skills,
prebuilt subagents, and model-aware on-demand spawned subagents.

The package does not replace ADK. It stays close to ADK's own `App`,
`LlmAgent`, `ToolContext`, `Runner`, `SkillToolset`, and event-stream
primitives.

## Highlights

- **Standard ADK return value**: `create_deep_agent(...)` returns a normal ADK `App`.
- **Built-in task ledger**: a session-backed `todo` tool for planning and progress tracking.
- **Automatic ledger context**: active todos are injected before model calls.
- **Structured elicitation**: optional native ADK `request_input` interruption with UI helpers.
- **Thinking support**: simple wrapper over ADK `BuiltInPlanner`.
- **Native compaction**: optional ADK event compaction with a deep-agent summary prompt.
- **Sandbox workspace**: optional shell and file tools backed by a local, Daytona, E2B, or Cloud Run sandbox, with credentials preflighted at build time.
- **Context caching**: optional ADK context caching for long sessions.
- **Tool flexibility**: accepts ADK `ToolUnion` values, including functions, `BaseTool`, `BaseToolset`, and MCP toolsets.
- **Skills**: accepts one developer-created ADK `SkillToolset`.
- **Prebuilt subagents**: attaches native ADK `sub_agents`.
- **Model-aware subagents**: exposes a validated model catalog to `spawn_subagent`.
- **On-demand subagents**: runs temporary children through ADK `ToolContext.run_node(...)`.
- **Streaming visibility**: raw ADK runner events include subagent activity; optional projection helpers are included.

## Installation

```bash
pip install adk-agent-harness
```

With uv:

```bash
uv add adk-agent-harness
```

Requirements:

- Python 3.10+
- `google-adk>=2.7.1,<3`

Optional extras install ADK's sandbox backends: `[daytona]`, `[e2b]`, or
`[sandbox]` for both.

Model clients and ADK services stay your choice. Pass any ADK `BaseLlm` as
`model_client` (for example `LiteLlm`, installed with `litellm` or
`google-adk[extensions]`), and give the ADK `Runner` whichever session,
artifact, or memory service your app uses. A Postgres `DatabaseSessionService`
needs SQLAlchemy and an async driver such as `asyncpg`, installed by your app.

## Quick Start

```python
from adk_agent_harness import create_deep_agent


def search_notes(query: str) -> str:
    """Search local notes."""

    return f"No notes backend configured for: {query}"


app = create_deep_agent(
    name="research_assistant",
    model_client="gemini-3-flash-preview",
    instruction="Investigate accurately and keep progress current.",
    tools=[search_notes],
)
```

Run it with the normal ADK `Runner`:

```python
from google.adk.runners import InMemoryRunner
from google.genai import types

runner = InMemoryRunner(app=app)
session = runner.session_service.create_session_sync(
    app_name=app.name,
    user_id="user",
)

for event in runner.run(
    user_id="user",
    session_id=session.id,
    new_message=types.Content(
        role="user",
        parts=[types.Part.from_text(text="Plan and research the task.")],
    ),
):
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                print(part.text)
```

## Factory API

```python
from adk_agent_harness import create_deep_agent

app = create_deep_agent(
    name="assistant",
    model_client="gemini-3-flash-preview",
    instruction="Help the user complete complex tasks.",
    tools=[],
)
```

`model_client` can be a model name string or an ADK `BaseLlm` instance.

## Structured User Elicitation

Set `elicitation=True` to attach ADK's native `request_input` long-running
tool and enable resumability on the returned `App`.

```python
app = create_deep_agent(
    name="interactive_agent",
    model_client="gemini-3-flash-preview",
    instruction="Ask for required decisions before taking irreversible action.",
    elicitation=True,
)
```

The model can request one or more answers with an object JSON schema. When the
runner emits the interruption, project it into a stable UI-facing request:

```python
from adk_agent_harness import (
    create_elicitation_response,
    project_elicitation_event,
)

request = project_elicitation_event(event)
if request is not None:
    # Render request.message and request.response_schema in the client.
    answers = {"environment": "production", "strategy": "canary"}
    response = create_elicitation_response(request, answers)

    async for resumed_event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        invocation_id=request.invocation_id,
        new_message=response,
    ):
        ...
```

While waiting, ADK makes no additional model call. The response helper creates
the user-role `FunctionResponse` with the original function-call ID so the
same invocation can continue.

## Task Ledger

Every deep agent includes a built-in `todo` tool. The ledger is stored in ADK
session state and reinjected into the model context before future model calls.

The tool supports:

- `todo()` to read the current ledger
- `todo(todos=[...])` to replace the ledger
- `todo(todos=[...], merge=True)` to update by ID and append new items

## Thinking And Compaction

```python
from adk_agent_harness import (
    CompactionConfig,
    ThinkingConfig,
    create_deep_agent,
)

app = create_deep_agent(
    name="configured_agent",
    model_client="gemini-3-flash-preview",
    instruction="Work carefully and keep track of progress.",
    thinking=ThinkingConfig(
        include_thoughts=True,
        thinking_budget=1024,
    ),
    compaction=CompactionConfig(token_threshold=48_000),
)
```

`thinking` maps to ADK `BuiltInPlanner`. `compaction` maps to ADK native event
compaction using a structured summarization prompt.

## Context Caching

Set `context_cache=True` to enable ADK context caching with its defaults, or
pass an ADK `ContextCacheConfig` to tune it. Caching pays off when a long
session keeps re-sending a large stable prefix (instructions, skills, tool
declarations).

```python
from google.adk.agents.context_cache_config import ContextCacheConfig

app = create_deep_agent(
    name="cached_agent",
    model_client="gemini-3-flash-preview",
    instruction="Work through long tasks with a stable toolset.",
    context_cache=ContextCacheConfig(
        cache_intervals=5,
        ttl_seconds=900,
        min_tokens=2048,
    ),
)
```

The value maps directly onto `App.context_cache_config`. Caching is off when
the argument is omitted.

## Sandbox Workspace

Set `sandbox=` to give the agent a workspace with shell and file tools. The
filesystem backends attach ADK's `EnvironmentToolset` (`Execute`, `ReadFile`,
`EditFile`, `WriteFile`) and ADK injects its own workspace instruction with the
working directory.

```python
from adk_agent_harness import SandboxConfig, create_deep_agent

app = create_deep_agent(
    name="workspace_agent",
    model_client="gemini-3-flash-preview",
    instruction="Work inside the provided workspace.",
    sandbox=SandboxConfig(kind="e2b", timeout=600),
)
```

`sandbox` accepts a backend name (`"local"`, `"daytona"`, `"e2b"`,
`"cloud_run"`), a `SandboxConfig`, or an ADK `BaseEnvironment` you built
yourself. The environment is created lazily on first use and closed with the
toolset.

### Backends And Required Environment Variables

| Backend | Install | Required env vars | Optional env vars | Provides |
| --- | --- | --- | --- | --- |
| `local` | included | none | none | shell + file tools |
| `daytona` | `pip install "adk-agent-harness[daytona]"` | `DAYTONA_API_KEY` | `DAYTONA_API_URL`, `DAYTONA_TARGET` | shell + file tools |
| `e2b` | `pip install "adk-agent-harness[e2b]"` | `E2B_API_KEY` | `E2B_DOMAIN` | shell + file tools |
| `cloud_run` | included | none | `K_SERVICE` | code execution only |

The `daytona` and `e2b` extras just pull the matching `google-adk` extra;
`adk-agent-harness[sandbox]` installs both.

Notes:

- `local` runs commands as subprocesses of your own process with no isolation.
  Prefer a remote sandbox for untrusted work.
- `daytona` and `e2b` accept `api_key` on the config instead of the environment
  variable; setting it satisfies the credential check.
- `cloud_run` attaches ADK's `CloudRunSandboxCodeExecutor` rather than file
  tools. It works only from inside a Cloud Run container deployed with the
  sandbox launcher (`gcloud beta run deploy --sandbox-launcher`), because it
  shells out to the guest binary at `/usr/local/gcp/bin/sandbox`.
- `env_vars` on the config are set *inside* the sandbox; they are not read from
  your process.

Credentials and optional packages are preflighted while the agent is built, so
a misconfigured backend raises `SandboxConfigurationError` immediately instead
of failing on the first tool call:

```python
from adk_agent_harness import (
    SandboxConfig,
    missing_sandbox_requirements,
    sandbox_requirements_report,
)

print(sandbox_requirements_report())          # full setup table
missing_sandbox_requirements(SandboxConfig(kind="e2b"))  # [] when ready
```

Pass `SandboxConfig(..., validate_environment=False)` to skip the preflight,
for example when building an agent in CI that will run elsewhere.

### Sharing The Workspace With Subagents

A prebuilt subagent opts in with `use_sandbox=True` and receives the *same*
workspace as the root agent. Spawned subagents can request it by the registry
name `environment`.

```python
from adk_agent_harness import SpawnConfig, SubAgentSpec
from adk_agent_harness.sandbox import SANDBOX_TOOLSET_NAME

app = create_deep_agent(
    name="workspace_agent",
    model_client="gemini-3-flash-preview",
    instruction="Delegate implementation work.",
    sandbox="local",
    subagents=[
        SubAgentSpec(name="builder", goal="Implement changes.", use_sandbox=True),
        SubAgentSpec(name="planner", goal="Draft a plan."),
    ],
    spawn=SpawnConfig(enabled=True, allowed_tools=[SANDBOX_TOOLSET_NAME]),
)
```

## Tools And MCP

Pass ordinary callables, ADK `BaseTool` values, or ADK `BaseToolset` values.
MCP toolsets are passed through the same `tools` argument.

```python
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

app = create_deep_agent(
    name="tool_agent",
    model_client="gemini-3-flash-preview",
    instruction="Use available tools when helpful.",
    tools=[
        my_function_tool,
        my_base_tool,
        McpToolset(...),
    ],
)
```

## Skills

Pass one ADK `SkillToolset` that you construct yourself:

```python
from adk_agent_harness import create_deep_agent
from google.adk.skills import models
from google.adk.tools import skill_toolset

status_skill = models.Skill(
    frontmatter=models.Frontmatter(
        name="status-skill",
        description="Summarize project status.",
    ),
    instructions="Use available project tools and return a concise summary.",
)

project_skills = skill_toolset.SkillToolset(skills=[status_skill])

app = create_deep_agent(
    name="skilled_agent",
    model_client="gemini-3-flash-preview",
    instruction="Use skills when they help.",
    skills=project_skills,
)
```

## Prebuilt Subagents

Prebuilt subagents use native ADK `sub_agents`. Use this when the developer
knows the child roles ahead of time.

```python
from adk_agent_harness import SubAgentSpec, create_deep_agent

app = create_deep_agent(
    name="main_agent",
    model_client="gemini-3-flash-preview",
    instruction="Delegate focused review work when useful.",
    subagents=[
        SubAgentSpec(
            name="reviewer",
            goal="Review delegated work and return risks.",
            mode="single_turn",
        )
    ],
)
```

Modes:

- `single_turn`: focused child work without user clarification
- `task`: ADK task mode with native task completion and resume behavior

## On-Demand Spawned Subagents

Enable `spawn_subagent` when the parent should create temporary specialists at
runtime. Spawned children are still ADK agents and run through
`ToolContext.run_node(...)`.

```python
from adk_agent_harness import ModelSpec, SpawnConfig, create_deep_agent


def inspect_code(path: str) -> str:
    """Inspect code at a path."""

    return f"No code inspection backend configured for: {path}"


app = create_deep_agent(
    name="main_agent",
    model_client="gemini-3-flash-preview",
    instruction="Spawn temporary specialists for bounded tasks.",
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
    spawn=SpawnConfig(
        enabled=True,
        tools={"inspect_code": inspect_code},
        allowed_tools=["inspect_code"],
    ),
)
```

The root instruction receives only model IDs and descriptive metadata. The
backend registry retains the actual model clients. `spawn_subagent` accepts an
optional `model` ID, defaults to the root model, and rejects unknown IDs.

Spawned agents always run in ADK `single_turn` mode, the same way ADK runs a
`single_turn` subagent: the child runs through `ToolContext.run_node(...)` on a
sub-branch keyed by the `spawn_subagent` function-call ID, receives `goal` and
`context` as its request, and returns its result as the tool response. Spawned
children never interact with the user, so `adk_request_input` is never offered
to them.

### Background Spawned Agents

The root agent decides per call whether to wait for a child. With
`spawn_subagent(..., background=true)` the tool returns
`{"status": "running", "task_id": ...}` immediately and the root agent keeps
working. There is nothing to configure.

- The child runs like ADK's `AgentTool` runs an agent: a separate `Runner` over
  its own in-memory session. No parent state is copied in or merged back, so the
  child is isolated from the root session.
- On the root agent's next model request, a `before_model_callback` lists
  still-running children and injects each finished result (or failure) once.
  An idle root agent sees the result when the client starts its next turn.
- Child events do not appear in the root `run_async()` stream. Read the child's
  raw ADK events, replayed from the start and then live, to translate them into
  your UI protocol such as AG-UI:

```python
from adk_agent_harness import stream_background_task_events, wait_for_background_task

async for event in stream_background_task_events(task_id):
    ...  # raw google.adk Event authored by the child

task = await wait_for_background_task(task_id)  # status, result, error
```

`get_background_task`, `list_background_tasks`, and `cancel_background_task`
are also available. At most four background children run at once per root
session. Background tasks live in process memory and do not survive a restart.

## Interrupted Tool Calls

A tool call can be left without a result when a run is cancelled or times out
mid-tool, the process crashes, or the user types instead of answering an
`adk_request_input` form. ADK still sends that unanswered call to the model, and
OpenAI, Anthropic, and Gemini reject or misbehave on a call with no result.

`create_deep_agent` always installs `ToolCallRepairPlugin` as the first App
plugin. Before every model request of every agent, including subagents and
background children, it inserts a synthetic `{"status": "interrupted"}` result
after each unanswered call. Only the outgoing request changes; stored session
history is never modified. If you build your own ADK `App`, add
`ToolCallRepairPlugin()` to its plugins, or call
`repair_dangling_tool_calls(llm_request.contents)` from a callback.

## Subagent Events

ADK streams subagent activity as ordinary runner events, so there is no package
event format to adopt. Prebuilt and foreground spawned children appear in the
root `run_async()` stream with `event.author` set to the child name and
`event.branch` set to `<parent>.<child>@<function-call-id>`. Translate them into
your UI protocol, such as AG-UI, like any other ADK event. Background children
stream through `stream_background_task_events(task_id)`.

## Examples

Numbered examples live in `examples/sdk`:

- `01_basic_task_ledger.py`
- `02_skills_and_toolsets.py`
- `03_thinking_compaction_plugins.py`
- `04_prebuilt_and_spawned_subagents.py`
- `05_elicitation_and_model_selection.py`
- `06_sandbox_and_context_cache.py`

## GitHub Topics

Suggested repository topics:

```text
adk
agent-development-kit
ai-agents
deep-agent
google-adk
llm
multi-agent
subagents
task-delegation
```

## Development

```bash
uv run python -m pytest tests/unit
uv build
uv run python -m twine check dist/*
```

## Publishing

See [`docs/PUBLISHING.md`](docs/PUBLISHING.md).

## License

MIT

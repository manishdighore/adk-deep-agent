<p align="center">
  <img src="https://raw.githubusercontent.com/manishdighore/adk-deep-agent/main/docs/assets/icon.svg" alt="adk-agent-harness" width="112" height="112">
</p>

<h3 align="center">adk-agent-harness</h3>

<p align="center">
  A deep-agent harness for Google ADK: planning, subagents, background work,<br>
  structured user input, and sandboxes, built on native ADK primitives.
</p>

<p align="center">
  <a href="https://pypi.org/project/adk-agent-harness/"><img alt="PyPI" src="https://img.shields.io/pypi/v/adk-agent-harness.svg"></a>
  <a href="https://pypi.org/project/adk-agent-harness/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/adk-agent-harness.svg"></a>
  <a href="https://github.com/manishdighore/adk-deep-agent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/manishdighore/adk-deep-agent/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://manishdighore.github.io/adk-deep-agent/"><img alt="Docs" src="https://img.shields.io/badge/docs-online-indigo.svg"></a>
  <a href="https://github.com/manishdighore/adk-deep-agent/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://github.com/google/adk-python"><img alt="Google ADK" src="https://img.shields.io/badge/Google%20ADK-2.7%2B-4285F4.svg"></a>
</p>

<p align="center">
  <a href="https://manishdighore.github.io/adk-deep-agent/"><b>Documentation</b></a> ·
  <a href="https://manishdighore.github.io/adk-deep-agent/getting-started/">Getting started</a> ·
  <a href="https://manishdighore.github.io/adk-deep-agent/reference/">API reference</a> ·
  <a href="https://github.com/manishdighore/adk-deep-agent/blob/main/CHANGELOG.md">Changelog</a>
</p>

`adk-agent-harness` turns a Google ADK agent into a **deep agent**: one that
plans, delegates to subagents, works in the background, asks the user for
structured input, and keeps long sessions on track.

It doesn't replace ADK. One factory, `create_deep_agent(...)`, returns a
standard `google.adk.apps.App`. You run it with an ordinary ADK `Runner`, your
own model client, and your own session service, and your UI receives ordinary
ADK events.

## What it adds to ADK

| Feature | What you get |
| --- | --- |
| **Task ledger** | A `todo` tool for plans and progress, stored in session state and shown to the model before every call |
| **Prebuilt subagents** | `SubAgentSpec`: children with their own model, tools, skills, thinking, and sandbox access |
| **Spawned subagents** | A `spawn_subagent` tool: the agent creates focused children at runtime from tools, skills, and models you allow |
| **Background subagents** | `background=true`: the child runs in isolation while the root agent continues, and its result is reported back automatically |
| **Model selection** | A validated catalog of models the agent can choose from for children |
| **Asking the user** | Structured questions with a JSON schema, pause and resume, and UI helpers |
| **Sandbox workspaces** | `local`, Daytona, E2B, or Cloud Run, with build-time credential checks and a workspace shared with subagents |
| **Interrupted tool calls** | Calls left without a result (cancel, crash, ignored form) are answered before the next model call, so providers don't reject the session |
| **Thinking, compaction, caching** | One-line settings, plus a compaction prompt written for long-running work |

## Install

```bash
pip install adk-agent-harness
```

Python 3.10+ and `google-adk>=2.7.1,<3`. Optional extras install ADK's remote
sandbox backends: `[daytona]`, `[e2b]`, or `[sandbox]` for both.

Model clients and session services are yours to choose: pass any ADK `BaseLlm`
as `model_client` (for example `LiteLlm` for OpenAI, Anthropic, or open-source
models), and give the `Runner` any ADK session service, such as
`DatabaseSessionService` for Postgres.

## Quick start

```python
import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from adk_agent_harness import SpawnConfig, create_deep_agent


def search_notes(query: str) -> str:
    """Search the team's notes."""
    return f"No notes found for: {query}"


app = create_deep_agent(
    name="research_assistant",
    model_client="gemini-3-flash-preview",
    instruction="Research thoroughly and keep your plan current.",
    tools=[search_notes],
    spawn=SpawnConfig(enabled=True),   # let the agent delegate to subagents
    elicitation=True,                  # let the agent ask structured questions
)


async def main() -> None:
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name=app.name, user_id="u1")
    message = types.Content(role="user", parts=[types.Part.from_text(text="Assess our Q3 launch risks.")])
    async for event in runner.run_async(user_id="u1", session_id=session.id, new_message=message):
        for part in event.content.parts if event.content else []:
            if part.text and not part.thought:
                print(f"[{event.author}] {part.text}")


asyncio.run(main())
```

## Features at a glance

### Subagents

```python
from adk_agent_harness import ModelSpec, SpawnConfig, SubAgentSpec

app = create_deep_agent(
    name="editor",
    model_client="gemini-3-flash-preview",
    instruction="Write the report and have it reviewed.",
    subagents=[SubAgentSpec(name="reviewer", goal="Review drafts for factual errors.")],
    available_models=[ModelSpec(id="strong", model_client="gemini-3-pro-preview",
                                description="Hard reasoning and review.")],
    spawn=SpawnConfig(enabled=True, tools={"fetch_url": fetch_url}),
)
```

Prebuilt subagents become tools named after them. `spawn_subagent` lets the
agent create a child on the fly. Both run like ADK's own single-turn subagents
and stream their events in the root `run_async()` stream.
[Subagents guide →](https://manishdighore.github.io/adk-deep-agent/guides/subagents/)

### Background subagents

The agent calls `spawn_subagent(..., background=true)`, gets a task ID
immediately, and keeps working. The result is added to its next model call.
Your app can stream the child's events separately:

```python
from adk_agent_harness import stream_background_task_events

async for event in stream_background_task_events(task_id):
    ...  # raw ADK events from the child
```

[Background subagents guide →](https://manishdighore.github.io/adk-deep-agent/guides/background-subagents/)

### Asking the user

```python
from adk_agent_harness import create_elicitation_response, project_elicitation_event

request = project_elicitation_event(event)   # the agent paused with a question
if request:
    reply = create_elicitation_response(request, {"environment": "staging"})
    async for event in runner.run_async(user_id=uid, session_id=sid,
                                        invocation_id=request.invocation_id, new_message=reply):
        ...
```

[Asking the user guide →](https://manishdighore.github.io/adk-deep-agent/guides/elicitation/)

### Sandbox workspaces

```python
app = create_deep_agent(..., sandbox="e2b")   # or "local", "daytona", "cloud_run"
```

The agent gets ADK's `Execute`, `ReadFile`, `WriteFile`, and `EditFile` tools.
Missing credentials fail when the agent is built, not on first use.
[Sandbox guide →](https://manishdighore.github.io/adk-deep-agent/guides/sandbox/)

### Long-running sessions

```python
from adk_agent_harness import CompactionConfig, ThinkingConfig

app = create_deep_agent(
    ...,
    thinking=ThinkingConfig(include_thoughts=True),
    compaction=CompactionConfig(token_threshold=100_000),
    context_cache=True,
)
```

[Thinking, compaction, caching guide →](https://manishdighore.github.io/adk-deep-agent/guides/context/)

## Examples

Runnable examples live in
[`examples/sdk`](https://github.com/manishdighore/adk-deep-agent/tree/main/examples/sdk):
the task ledger, skills and toolsets, thinking and compaction, subagents,
elicitation and model selection, and sandboxes.

## Development

```bash
uv sync                              # dev tools included
uv run python -m pytest tests/unit
uv sync --group docs && uv run mkdocs serve   # docs at http://127.0.0.1:8000
```

Releases: see
[`docs/PUBLISHING.md`](https://github.com/manishdighore/adk-deep-agent/blob/main/docs/PUBLISHING.md).

## License

MIT

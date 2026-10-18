# Getting started

## Install

=== "pip"

    ```bash
    pip install adk-agent-harness
    ```

=== "uv"

    ```bash
    uv add adk-agent-harness
    ```

Requires Python 3.10+ and `google-adk>=2.7.1,<3`.

Optional extras install ADK's remote sandbox backends:

| Extra | Installs | Use for |
| --- | --- | --- |
| `adk-agent-harness[daytona]` | `google-adk[daytona]` | Daytona sandboxes |
| `adk-agent-harness[e2b]` | `google-adk[e2b]` | E2B sandboxes |
| `adk-agent-harness[sandbox]` | both | Either backend |

Model clients and session services are not extras. You install and pass
whichever ones your app uses (see [below](#choose-a-model)).

## Create an agent

```python
from adk_agent_harness import create_deep_agent


def search_notes(query: str) -> str:
    """Search the team's notes."""
    return f"No notes found for: {query}"


app = create_deep_agent(
    name="research_assistant",
    model_client="gemini-3-flash-preview",
    instruction="Investigate accurately and keep your plan current.",
    tools=[search_notes],
)
```

`app` is a standard ADK `App`. Without any options it already has:

- your tools;
- the built-in [`todo` task ledger](guides/task-ledger.md), shown to the model
  before every call;
- [`ToolCallRepairPlugin`](guides/tool-call-repair.md).

## Run it

Use any ADK `Runner`. Here, the in-memory one:

```python
import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types


async def main() -> None:
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id="user-1",
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Plan and research our Q3 launch risks.")],
    )
    async for event in runner.run_async(
        user_id="user-1",
        session_id=session.id,
        new_message=message,
    ):
        for part in event.content.parts if event.content else []:
            if part.text and not part.thought:
                print(f"[{event.author}] {part.text}")


asyncio.run(main())
```

Every event is a normal ADK event, including those from subagents. See
[Streaming to a UI](guides/streaming.md).

## Choose a model

`model_client` accepts a model name string or any ADK `BaseLlm`. For OpenAI,
Anthropic, or open-source models, use ADK's `LiteLlm` (install `litellm` or
`google-adk[extensions]`):

```python
from google.adk.models.lite_llm import LiteLlm

app = create_deep_agent(
    name="assistant",
    model_client=LiteLlm(model="anthropic/claude-sonnet-4-5"),
    instruction="Help the user complete complex tasks.",
)
```

Provider credentials stay in your environment, as with plain ADK.

## Keep sessions in a database

The session service belongs to the runner, not the package. For Postgres, use
ADK's `DatabaseSessionService` with an async driver such as `asyncpg`:

```python
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

runner = Runner(
    app=app,
    session_service=DatabaseSessionService(
        "postgresql+asyncpg://user:password@host/dbname"
    ),
)
```

The task ledger, the history of prebuilt and foreground subagents, and pending
questions to the user are stored in the session, so they persist with it.
[Background subagents](guides/background-subagents.md) are the exception: they
run in process memory.

## Next steps

- [Subagents](guides/subagents.md): delegate to prebuilt or spawned children.
- [Asking the user](guides/elicitation.md): pause for structured input.
- [Sandbox workspaces](guides/sandbox.md): give the agent files and a shell.
- [API reference](reference.md): every public class and function.

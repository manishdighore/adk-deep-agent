# Background subagents

With [spawning enabled](subagents.md#spawned-subagents), the root agent decides
per call whether to wait for a child. When it passes `background=true`,
`spawn_subagent` returns immediately and the root agent keeps working:

```json
{"status": "running", "task_id": "4f1c…", "name": "researcher", "model": "strong"}
```

There's nothing to configure. It's the model's choice, guided by the tool
description: use it for independent work it doesn't need before continuing.

## Isolation

A background child runs the way ADK's `AgentTool` runs an agent: in a separate
`Runner` with its own in-memory session, artifacts, and memory. Unlike
`AgentTool`, **no session state is copied in or merged back**, so the child
can't read or change the root session. It shares only:

- the App's plugins (including [`ToolCallRepairPlugin`](tool-call-repair.md))
  and credential service;
- the sandbox, if the agent gave the child the `environment` tool.

A background child gets the same tools, instruction, and request as a
foreground one. It still can't ask the user anything.

## How results come back

Before each root model request, the root agent is told:

- which background children are **still running**, so it doesn't redo or wait
  for that work;
- the **result or failure** of each child that finished since its last turn.
  Results are shown once, and long results are cut at 8,000 characters.

If the root agent is idle when a child finishes, it sees the result on its
next turn. To report back without waiting for the user, have your app start a
turn when the task finishes (see the example below).

## Streaming a child's events

Background children don't appear in the root `run_async()` stream, which has
usually finished by then. Read them from the task instead:

```python
from adk_agent_harness import stream_background_task_events

async for event in stream_background_task_events(task_id):
    ...  # a raw google.adk Event authored by the child
```

The iterator replays every event from the start, then follows live ones, and
ends when the task finishes. A client that connects late gets the full
history.

## Example: forward events and wake the root agent

```python
import asyncio

from adk_agent_harness import stream_background_task_events, wait_for_background_task
from adk_agent_harness.subagents import SPAWN_TOOL_NAME
from google.genai import types


async def follow_background_task(runner, user_id, session_id, task_id, send_to_ui):
    async for event in stream_background_task_events(task_id):
        await send_to_ui(task_id, event)          # translate to AG-UI, SSE, etc.

    task = await wait_for_background_task(task_id)
    # Start a root turn so the agent reports the result right away.
    note = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Background task {task.name} finished.")],
    )
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=note
    ):
        await send_to_ui(None, event)


# While streaming a root turn, start a follower for each background spawn.
async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=msg):
    for response in event.get_function_responses():
        if response.name == SPAWN_TOOL_NAME and response.response.get("status") == "running":
            asyncio.create_task(
                follow_background_task(
                    runner, user_id, session_id, response.response["task_id"], send_to_ui
                )
            )
    await send_to_ui(None, event)
```

!!! warning "One turn per session at a time"
    Don't start the wake-up turn while another turn on the same root session is
    still running. ADK's database session services reject writes to a session
    that changed underneath them. Queue the wake-up until the current turn ends.

## Managing tasks

| Function | Returns |
| --- | --- |
| `get_background_task(task_id)` | `BackgroundTask` (status, result, error, timestamps) or `None` |
| `list_background_tasks(session_id=...)` | Tasks started from that root session, oldest first |
| `wait_for_background_task(task_id)` | The final `BackgroundTask`, once it finishes |
| `cancel_background_task(task_id)` | `True` if it was running and is now cancelled |
| `stream_background_task_events(task_id)` | Async iterator of the child's raw ADK events |

Status is `running`, `completed`, `failed`, or `cancelled`.

## Limits

- **Up to 4 running at once per root session.** A fifth spawn returns an error
  asking the agent to wait.
- **Process memory only.** Tasks and their events are tracked in the running
  process (the 200 most recent finished tasks are kept). They don't survive a
  restart and aren't shared between server processes.
- **Default ADK mode.** ADK doesn't allow a `single_turn` agent as the root of a
  `Runner`, so background children use ADK's default mode, as `AgentTool` does.
  They still receive one request and have no way to reach the user.

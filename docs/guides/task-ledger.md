# Task ledger

Every agent built with `create_deep_agent` gets a `todo` tool. The model uses it
to write down a plan, mark progress, and pick up where it left off. You don't
configure anything.

## How the model uses it

| Call | Effect |
| --- | --- |
| `todo()` | Read the current list |
| `todo(todos=[...])` | Replace the list with a fresh plan |
| `todo(todos=[...], merge=True)` | Update items by `id` and append new ones, keeping order |

Each item is `{id, content, status}`, where `status` is `pending`,
`in_progress`, `completed`, or `cancelled`. List order is priority. The tool
always returns the full list plus counts per status:

```json
{
  "todos": [
    {"id": "1", "content": "Collect Q3 incident reports", "status": "completed"},
    {"id": "2", "content": "Group incidents by root cause", "status": "in_progress"},
    {"id": "3", "content": "Draft the risk summary", "status": "pending"}
  ],
  "summary": {"total": 3, "pending": 1, "in_progress": 1, "completed": 1, "cancelled": 0}
}
```

The tool's description and rules follow the Hermes agent's `todo` tool: keep
one item in progress, mark items done immediately, and cancel and replace items
that fail.

## What keeps it on track

- **Shown before every model call.** Before each root model request, pending
  and in-progress items are added to the instructions under "Current task
  ledger. Continue from this state; do not repeat completed work." Finished
  items are left out so the model doesn't redo them.
- **Survives compaction.** The list lives in session state, not in the
  conversation, so [compaction](context.md#compaction) can't summarize it away.
- **One write per response.** If the model issues two `todo` writes in one
  response, which ADK could run in parallel, the response is rejected and the
  model is asked to write once.

## Where it's stored

The ledger is stored in session state under `LEDGER_STATE_KEY`
(`"adk_agent_harness:todos"`), so it persists with whatever session service
your runner uses. Your UI can read it from the session's state, or from the
`todo` tool calls and results in the event stream.

```python
from adk_agent_harness import LEDGER_STATE_KEY

session = await runner.session_service.get_session(
    app_name=app.name, user_id=user_id, session_id=session_id
)
todos = session.state.get(LEDGER_STATE_KEY, [])
```

## Limits

- At most 100 items.
- `id` up to 80 characters, `content` up to 1,000 characters.
- Duplicate IDs are rejected with an error, and the stored list is unchanged.
- The ledger belongs to the root agent. Subagents don't get their own.

# Running in production

The package builds an ADK `App`. Everything around it (sessions, servers,
users, scaling) works the way ADK does. This page covers the points where the
package's features meet that infrastructure.

## Sessions

Use a persistent ADK session service, such as `DatabaseSessionService` for
Postgres (install SQLAlchemy and an async driver like `asyncpg` in your app).
The task ledger, prebuilt and foreground subagent history, and pending
questions to the user are all stored in the session.

**Run one turn per session at a time.** ADK's database session services reject
writes to a session that changed after it was loaded, so queue new messages
for a session until its current turn finishes.

## Users and sandboxes

A sandbox belongs to the App, and every session of that App shares it. For
per-user isolation, create one App and `Runner` per user with that user's
environment, cache them, and call `runner.close()` when the user is idle or
done, which removes the sandbox. See
[Sandbox workspaces](sandbox.md#lifetime-one-sandbox-per-app).

## Background subagents

Background tasks are tracked in the memory of the process that started them:

- route a session's requests to the same process (sticky sessions) while it
  has background tasks running;
- expect running tasks to be lost on restart or deploy;
- forward each task's events and start the "task finished" turn from that
  process. See the
  [example](background-subagents.md#example-forward-events-and-wake-the-root-agent).

## Asking the user

`elicitation=True` makes the App resumable. Keep the `invocation_id` from the
`ElicitationRequest` with your pending UI state, so the answer can resume the
interrupted run, even after a page reload.

## Long sessions

- Set [`compaction`](context.md#compaction) with a `token_threshold` well below
  your model's context window.
- Consider [`context_cache`](context.md#context-caching) when instructions,
  skills, and tools are large and stable.
- `event.usage_metadata` reports token counts per model call if you want to
  track cost or context use.

## Versions

The package depends on `google-adk>=2.7.1,<3` and uses some ADK features still
marked experimental: `EnvironmentToolset`, the Daytona and E2B environments,
and resumable Apps. Pin the versions you've tested in your app and upgrade
deliberately.

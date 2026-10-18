"""Background spawned subagents for adk-agent-harness.

`spawn_subagent(..., background=True)` starts the child the way ADK's
`AgentTool` runs an agent: a separate `Runner` over its own in-memory session.
Unlike `AgentTool`, parent state is neither copied into the child nor merged
back, so a background child is fully isolated from the root session.

The tool returns a task ID immediately and the root agent keeps working.
Every raw ADK event the child emits is buffered here so a client can replay
and follow it with `stream_background_task_events(task_id)`. When the child
finishes, `inject_background_task_updates` reports the result to the root
agent on its next model request.

Background tasks are tracked in this process only. They do not survive a
process restart, and an idle root agent only sees a finished result once the
client starts a new turn on the root session.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.events.event import Event
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import BaseModel

BackgroundTaskStatus = Literal["running", "completed", "failed", "cancelled"]

MAX_RUNNING_BACKGROUND_TASKS = 4
"""Maximum concurrently running background children per root session."""

MAX_RETAINED_FINISHED_TASKS = 200
"""Finished task records kept in memory for status and stream replay."""

MAX_INJECTED_RESULT_CHARS = 8000
"""Truncation limit for one background result injected into root context."""


class BackgroundTask(BaseModel):
    """Status of one background spawned subagent."""

    task_id: str
    name: str
    goal: str
    model: str
    app_name: str
    user_id: str
    parent_session_id: str
    status: BackgroundTaskStatus = "running"
    result: Any = None
    error: str | None = None
    created_at: float
    finished_at: float | None = None


class _TaskRecord:
    def __init__(self, task: BackgroundTask) -> None:
        self.task = task
        self.events: list[Event] = []
        self.changed = asyncio.Condition()
        self.runner_task: asyncio.Task[None] | None = None
        self.reported_invocation_id: str | None = None

    @property
    def done(self) -> bool:
        return self.task.status != "running"

    @property
    def session_key(self) -> tuple[str, str, str]:
        return (self.task.app_name, self.task.user_id, self.task.parent_session_id)

    async def append(self, event: Event) -> None:
        async with self.changed:
            self.events.append(event)
            self.changed.notify_all()

    async def finish(self, **update: Any) -> None:
        async with self.changed:
            self.task = self.task.model_copy(
                update={**update, "finished_at": time.time()}
            )
            self.changed.notify_all()


_records: dict[str, _TaskRecord] = {}


def _require(task_id: str) -> _TaskRecord:
    record = _records.get(task_id)
    if record is None:
        raise KeyError(f"unknown background task: {task_id}")
    return record


def _prune_finished() -> None:
    finished = [record for record in _records.values() if record.done]
    excess = len(finished) - MAX_RETAINED_FINISHED_TASKS
    if excess <= 0:
        return
    finished.sort(key=lambda record: record.task.finished_at or 0)
    for record in finished[:excess]:
        _records.pop(record.task.task_id, None)


def _final_text(event: Event) -> str | None:
    if event.partial or not event.content or not event.content.parts:
        return None
    texts = [part.text for part in event.content.parts if part.text and not part.thought]
    return "\n".join(texts) if texts else None


async def _run_child(
    record: _TaskRecord,
    runner: Any,
    *,
    session_id: str,
    user_id: str,
    request: str,
) -> None:
    last_text: str | None = None
    last_error: str | None = None
    try:
        async with contextlib.aclosing(
            runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=request)],
                ),
            )
        ) as agen:
            async for event in agen:
                await record.append(event)
                if event.error_message:
                    last_error = event.error_message
                text = _final_text(event)
                if text:
                    last_text = text
        if last_text is None and last_error:
            await record.finish(status="failed", error=last_error)
        else:
            await record.finish(status="completed", result=last_text or "")
    except asyncio.CancelledError:
        await record.finish(status="cancelled", error="cancelled")
        raise
    except Exception as exc:
        await record.finish(status="failed", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await runner.close()
        _prune_finished()


async def start_background_child(
    child: Agent,
    *,
    request: str,
    goal: str,
    model_id: str,
    tool_context: ToolContext,
) -> BackgroundTask:
    """Start an isolated background run of a spawned child agent."""

    from google.adk.runners import Runner

    invocation_context = tool_context.get_invocation_context()
    app_name = invocation_context.app_name
    user_id = tool_context.user_id
    parent_session_id = tool_context.session.id
    session_key = (app_name, user_id, parent_session_id)

    running = [
        record
        for record in _records.values()
        if record.session_key == session_key and not record.done
    ]
    if len(running) >= MAX_RUNNING_BACKGROUND_TASKS:
        raise ValueError(
            f"at most {MAX_RUNNING_BACKGROUND_TASKS} background subagents can "
            "run at once; wait for one to finish"
        )

    # Mirror ADK's AgentTool runner, but share no session state or artifacts.
    runner = Runner(
        app_name=app_name,
        agent=child,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
        credential_service=invocation_context.credential_service,
        plugins=invocation_context.plugin_manager.plugins,
    )
    runner.plugin_manager.set_skip_closing_plugins(True)
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
    )

    task = BackgroundTask(
        task_id=uuid.uuid4().hex,
        name=child.name,
        goal=goal,
        model=model_id,
        app_name=app_name,
        user_id=user_id,
        parent_session_id=parent_session_id,
        created_at=time.time(),
    )
    record = _TaskRecord(task)
    _records[task.task_id] = record
    record.runner_task = asyncio.create_task(
        _run_child(
            record,
            runner,
            session_id=session.id,
            user_id=user_id,
            request=request,
        ),
        name=f"adk_agent_harness:background:{task.task_id}",
    )
    return task


def get_background_task(task_id: str) -> BackgroundTask | None:
    """Return the current status of one background task."""

    record = _records.get(task_id)
    return record.task if record else None


def list_background_tasks(
    *,
    session_id: str,
    app_name: str | None = None,
    user_id: str | None = None,
) -> list[BackgroundTask]:
    """Return background tasks started from one root session, oldest first."""

    tasks = [
        record.task
        for record in _records.values()
        if record.task.parent_session_id == session_id
        and (app_name is None or record.task.app_name == app_name)
        and (user_id is None or record.task.user_id == user_id)
    ]
    return sorted(tasks, key=lambda task: task.created_at)


async def stream_background_task_events(task_id: str) -> AsyncIterator[Event]:
    """Yield the child's raw ADK events: buffered ones first, then live ones.

    The iterator ends when the background task finishes.
    """

    record = _require(task_id)
    index = 0
    while True:
        async with record.changed:
            while index >= len(record.events) and not record.done:
                await record.changed.wait()
            batch = record.events[index:]
            index = len(record.events)
            done = record.done
        for event in batch:
            yield event
        if done and index >= len(record.events):
            return


async def wait_for_background_task(task_id: str) -> BackgroundTask:
    """Wait until a background task finishes and return its final status."""

    record = _require(task_id)
    async with record.changed:
        await record.changed.wait_for(lambda: record.done)
    return record.task


def cancel_background_task(task_id: str) -> bool:
    """Cancel a running background task. Returns False if it already finished."""

    record = _require(task_id)
    if record.done or record.runner_task is None:
        return False
    return record.runner_task.cancel()


def _format_result(task: BackgroundTask) -> str:
    if task.status == "completed":
        text = str(task.result)
        if len(text) > MAX_INJECTED_RESULT_CHARS:
            text = text[:MAX_INJECTED_RESULT_CHARS] + "\n[result truncated]"
        return f"completed. Result:\n{text}"
    return f"{task.status}: {task.error or 'no details'}"


def format_background_task_updates(
    records: list[_TaskRecord],
    *,
    invocation_id: str,
) -> str | None:
    """Format running and newly finished background tasks for root context."""

    running = [record.task for record in records if not record.done]
    finished = [
        record
        for record in records
        if record.done and record.reported_invocation_id in {None, invocation_id}
    ]
    if not running and not finished:
        return None

    lines = ["Background subagent updates."]
    if running:
        lines.append("Still running (do not wait for or repeat this work):")
        lines.extend(
            f"- `{task.name}` (task `{task.task_id}`): {task.goal}" for task in running
        )
    if finished:
        lines.append(
            "Finished since your last turn. Use these results now; they are not "
            "repeated in later turns:"
        )
        for record in finished:
            record.reported_invocation_id = invocation_id
            task = record.task
            lines.append(
                f"- `{task.name}` (task `{task.task_id}`, goal: {task.goal}) "
                f"{_format_result(task)}"
            )
    return "\n".join(lines)


def inject_background_task_updates(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Report background subagent status and results to the root agent."""

    session = callback_context.session
    session_key = (session.app_name, session.user_id, session.id)
    records = sorted(
        (record for record in _records.values() if record.session_key == session_key),
        key=lambda record: record.task.created_at,
    )
    updates = format_background_task_updates(
        records,
        invocation_id=callback_context.invocation_id,
    )
    if updates:
        llm_request.append_instructions([updates])
    return None

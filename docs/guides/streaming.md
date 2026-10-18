# Streaming to a UI

The package has no event format of its own. Everything your UI needs arrives
as standard ADK `Event` objects from `runner.run_async()`, so any ADK client
or protocol adapter, such as one for AG-UI or CopilotKit, works unchanged.

## Reading an event

| What to show | Where it is in the event |
| --- | --- |
| Assistant text | `part.text` where `part.thought` is false |
| Reasoning | `part.text` where `part.thought` is true (needs [`include_thoughts=True`](context.md#thinking)) |
| Tool call started | `event.get_function_calls()`: name, args, id |
| Tool result | `event.get_function_responses()`: name, response, id |
| Which agent | `event.author`: the root's name or a subagent's |
| Which delegation | `event.branch`, for example `editor.reviewer@<call-id>` |
| A question for the user | `project_elicitation_event(event)` is not `None` (see [Asking the user](elicitation.md)) |
| Token usage | `event.usage_metadata`: prompt, output, reasoning, and cached token counts |
| Streaming chunk | `event.partial` is true (with `RunConfig(streaming_mode=StreamingMode.SSE)`) |

These map onto AG-UI's text message, reasoning, tool call, and tool call result
events.

## Subagent activity

Prebuilt and foreground spawned subagents stream **inside the root stream**, in
order, between the root's tool call and its tool result:

```text
author=editor    call   reviewer(request=…)        ← root delegates
author=reviewer  call   search_sources(…)          ← child's tool call
author=reviewer  result search_sources             ← child's tool result
author=reviewer  thought …                         ← child's reasoning
author=reviewer  text   "Two claims need sources…" ← child's answer
author=editor    result reviewer                   ← back to the root
author=editor    text   "Revised report: …"
```

To group a child's events in the UI, use `event.author`, or `event.branch` to
tell two calls to the same child apart. The call ID in the branch matches the
root's tool call that started the child.

[Background subagents](background-subagents.md) are the exception: their events
come from `stream_background_task_events(task_id)`, a separate stream you can
forward on its own channel.

## Minimal example

```python
async for event in runner.run_async(user_id=uid, session_id=sid, new_message=msg):
    who = event.author
    for call in event.get_function_calls():
        ui.tool_started(who, call.id, call.name, call.args)
    for response in event.get_function_responses():
        ui.tool_finished(who, response.id, response.name, response.response)
    for part in event.content.parts if event.content else []:
        if part.text:
            (ui.reasoning if part.thought else ui.text)(who, part.text)
```

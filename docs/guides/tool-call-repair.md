# Interrupted tool calls

OpenAI, Anthropic, and Gemini expect every tool call in a conversation to be
followed by its result. A call without one makes the provider reject the
request, and because the call stays in history, every later turn in that
session fails too.

## When it happens

- A run is **cancelled or times out** while a tool is running.
- The **process crashes** mid-tool.
- The user **types a message instead of answering** an
  [`adk_request_input` form](elicitation.md).
- A client adapter leaves a client-side tool call unanswered.

ADK removes results that have no matching call, but it still sends a call that
has no result.

## What the package does

`create_deep_agent` always installs `ToolCallRepairPlugin` as the App's first
plugin. Before **every model request of every agent**, it finds each tool call
without a result and inserts one right after it:

```json
{
  "status": "interrupted",
  "error": "This tool call did not complete because the run was interrupted before a result was recorded. Do not assume it succeeded; call the tool again if the result is still needed."
}
```

- **Every agent is covered:** the root, prebuilt and spawned subagents, and
  background children, whose runner inherits the App's plugins.
- **Parallel calls stay paired.** If only some calls in one model message have
  results, the missing ones are added to that same result message.
- **History is untouched.** Only the outgoing request changes. Stored session
  events are never modified.
- **Matching:** by call ID when both sides have one (OpenAI and Anthropic IDs
  are kept), otherwise by tool name in the result message that immediately
  follows. ADK strips its own `adk-` IDs before callbacks run, and this is the
  layout ADK itself produces.

It's safe to run on every request: ADK never calls the model while a tool is
legitimately still waiting, so any call without a result at that point was
interrupted.

## Using it without `create_deep_agent`

```python
from google.adk.apps import App

from adk_agent_harness import ToolCallRepairPlugin, repair_dangling_tool_calls

app = App(name="my_app", root_agent=agent, plugins=[ToolCallRepairPlugin()])

# Or inside your own before_model_callback:
def before_model(callback_context, llm_request):
    repair_dangling_tool_calls(llm_request.contents)  # returns how many it added
```

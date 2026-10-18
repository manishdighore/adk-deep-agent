# Asking the user

Set `elicitation=True` and the agent can stop to ask the user structured
questions: a message plus a JSON Schema describing the answer, rendered by your
UI as a form. This is ADK's native `request_input` tool. The package adds it to
the root agent, makes the `App` resumable, and gives you helpers for the client
side.

```python
app = create_deep_agent(
    name="deployer",
    model_client="gemini-3-flash-preview",
    instruction="Confirm the target environment before deploying.",
    elicitation=True,
)
```

## The flow

1. **The agent asks.** It calls `adk_request_input(message, response_schema)`.
   ADK treats it as a long-running tool and **stops the run**. No further model
   call is made while it waits.
2. **Your client shows the question.** `project_elicitation_event(event)`
   returns an `ElicitationRequest` for the event that carries the question, and
   `None` for every other event.
3. **The user answers.** `create_elicitation_response(request, answers)` builds
   the user-role `FunctionResponse` with the same call ID.
4. **The run resumes.** Send that response with the interrupted
   `invocation_id`. ADK pairs it with the waiting call and the model receives
   `{"result": answers}`.

```python
from adk_agent_harness import create_elicitation_response, project_elicitation_event

pending = None
async for event in runner.run_async(user_id=uid, session_id=sid, new_message=msg):
    if (request := project_elicitation_event(event)) is not None:
        pending = request

if pending is not None:
    # Render pending.message and pending.response_schema, collect answers.
    answers = {"environment": "staging", "notify_team": True}
    async for event in runner.run_async(
        user_id=uid,
        session_id=sid,
        invocation_id=pending.invocation_id,
        new_message=create_elicitation_response(pending, answers),
    ):
        ...
```

`ElicitationRequest` fields: `id` (call ID), `message`, `response_schema`,
`invocation_id`, `author` (the agent that asked), and `raw_event`.

## Schemas the model is told to use

The root instruction tells the model to ask once with an object schema covering
all related questions, using standard JSON Schema: `title` and `description`
for labels, `enum` for choices, `boolean` for confirmations, arrays for
multi-select, and `required` for mandatory answers.

```json
{
  "type": "object",
  "properties": {
    "environment": {"type": "string", "title": "Environment", "enum": ["staging", "production"]},
    "notify_team": {"type": "boolean", "title": "Notify the team?"}
  },
  "required": ["environment"]
}
```

## Who can ask

| Agent | Can ask the user |
| --- | --- |
| Root | When `elicitation=True` |
| Prebuilt subagent in `task` mode | When you add ADK's `request_input` to its `tools` |
| Prebuilt subagent in `single_turn` mode | No: it's designed to run without user interaction |
| Spawned subagent (foreground or background) | Never: the answer couldn't be routed back to it |

## If the user types instead of answering

If the next message is plain text rather than the `FunctionResponse`, the
question is left without an answer. [`ToolCallRepairPlugin`](tool-call-repair.md)
marks it as not completed before the next model call, so the model sees that
the question went unanswered alongside the user's new message, and the
provider doesn't reject the request. Your UI should still guide users to answer
the form.

!!! note "Using CopilotKit or another AG-UI client"
    Make sure your adapter sends the answer back as a `FunctionResponse` with the
    original call ID and resumes with the same `invocation_id`, as in step 4.

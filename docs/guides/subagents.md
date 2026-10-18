# Subagents

A subagent is a child agent the root agent delegates a focused job to. Both
kinds below look the same to the root model, a tool call that returns the
child's result, and both run the way ADK runs a `single_turn` subagent: on
their own branch of the root session, with their events in the root
`run_async()` stream.

| | Prebuilt (`SubAgentSpec`) | Spawned (`spawn_subagent`) |
| --- | --- | --- |
| Who defines it | You, in code | The root agent, at runtime |
| How the root calls it | A tool named after the child | The `spawn_subagent` tool |
| Tools and skills | Whatever you give it | Chosen by the agent from what you allow |
| Model | Fixed per spec | Chosen by the agent from [your catalog](models.md) |
| Modes | `single_turn` (default) or `task` | Always `single_turn` |
| Thinking | Configurable | Not set |
| Can ask the user | In `task` mode, if you give it `request_input` | Never |
| Background | No | Yes, with [`background=true`](background-subagents.md) |
| Lifetime | Lasts as long as the App | Built for one call, then discarded |

## Prebuilt subagents

Declare children you know ahead of time:

```python
from adk_agent_harness import SubAgentSpec, create_deep_agent

app = create_deep_agent(
    name="editor",
    model_client="gemini-3-flash-preview",
    instruction="Write the report, then have it reviewed before finishing.",
    subagents=[
        SubAgentSpec(
            name="reviewer",
            goal="Review drafts for factual errors and unclear claims.",
            model_client="gemini-3-pro-preview",
            tools=[search_sources],
        ),
    ],
)
```

They're attached as native ADK `sub_agents`. ADK exposes each one to the root
agent as a tool named after the child (here `reviewer(request=...)`), runs it,
and returns its output as the tool result.

- **`goal`** builds a default instruction and the tool description. Pass
  `instruction` or `description` to override either.
- **`model_client`** defaults to the root model.
- **`mode`**:
    - `single_turn` (default): the child does the job in one go without user
      interaction.
    - `task`: ADK task mode. The child can go back and forth until it calls
      ADK's `finish_task`. Add ADK's `request_input` to its `tools` if it
      should be able to ask the user (see [Asking the user](elicitation.md)).
- **`thinking`** takes the same values as the root's `thinking`.
- **`use_sandbox=True`** gives the child the root's
  [sandbox workspace](sandbox.md#sharing-the-workspace-with-subagents).

Names must be valid Python identifiers, can't be `user`, and must be unique
across the root and all subagents.

## Spawned subagents

Let the root agent create focused children when it needs them:

```python
from adk_agent_harness import ModelSpec, SpawnConfig, create_deep_agent

app = create_deep_agent(
    name="analyst",
    model_client="gemini-3-flash-preview",
    instruction="Break large analyses into focused delegated tasks.",
    tools=[query_warehouse],
    available_models=[
        ModelSpec(
            id="strong",
            model_client="gemini-3-pro-preview",
            description="Hard reasoning and careful review.",
        ),
    ],
    spawn=SpawnConfig(
        enabled=True,
        tools={"fetch_url": fetch_url},
        allowed_tools=["query_warehouse", "fetch_url"],
    ),
)
```

This adds a `spawn_subagent` tool to the root agent.

### The tool the model calls

| Argument | Meaning |
| --- | --- |
| `name` | Name for the child; must not clash with existing agents |
| `goal` | What the child must accomplish |
| `context` | Optional details from the parent the child needs |
| `tool_names` | Tools to give the child, from the allowed set |
| `skill_names` | Skill toolsets to give the child, from the allowed set |
| `model` | A model ID from the [catalog](models.md); defaults to the root model |
| `background` | Run without waiting; see [Background subagents](background-subagents.md) |

It returns `{"status": "completed", "name", "model", "result"}` or
`{"status": "error", "name", "error"}`. Errors cover unknown or disallowed
tools, skills, or models, and name clashes.

### What the child gets

- **Tools:** only those it was given. The tools it can choose from are the
  root's `tools`, `SpawnConfig.tools`, and the sandbox as `environment` when
  one is configured, filtered by `allowed_tools` if you set it (empty allows
  all). Skills work the same way through `SpawnConfig.skills` and
  `allowed_skills`.
- **Instruction:** its role, and that it must work from the request and can't
  ask the user questions.
- **Request:** `Goal: …` followed by `Context from parent: …`.
- **No user access:** ADK's `adk_request_input` is never offered to spawned
  children, even if listed, because an answer couldn't be routed back to a
  child that no longer exists.
- **No nesting:** children can't spawn further children.

### How it runs

Exactly like ADK's own single-turn subagent tool: the child is built with
`mode="single_turn"` and run with `ToolContext.run_node(...)` on the branch
`<root>.<child>@<function-call-id>`. Its tool calls, results, reasoning, and
text stream in the root `run_async()` stream, tagged with the child's name as
`event.author`, and are saved in the root session.

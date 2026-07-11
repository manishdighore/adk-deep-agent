# ADK Deep Agent: Implementation Plan

Status: Phase 1, Phase 2, and elicitation/model-selection additions implemented
Target package: `adk-deep-agent`  
Python package: `adk_deep_agent`  
Updated: 2026-07-12

This document specifies the ADK implementation work. Architecture comparisons and broader feature decisions remain in `ADK-DEEP-AGENT.md`.

## Phase 1 Deliverable

Implement a factory that creates a standard Google ADK `App` containing a configured root `LlmAgent`:

```python
from adk_deep_agent import (
    CompactionConfig,
    ThinkingConfig,
    create_deep_agent,
)

app = create_deep_agent(
    name="research_assistant",
    model_client=model_client,
    instruction="Investigate accurately and keep progress current.",
    tools=[search_tool],
    skills=project_skills,
    thinking=ThinkingConfig(
        enabled=True,
        include_thoughts=True,
        thinking_budget=1024,
    ),
    compaction=CompactionConfig(token_threshold=48000),
)
```

The created app includes:

1. A caller-supplied model name or ADK model client.
2. A caller-supplied base instruction and tools.
3. A built-in session-backed `todo` task-ledger tool.
4. A built-in root-agent callback that injects active ledger items before each model call.
5. One developer-created ADK `SkillToolset` attached to the root agent when supplied.
6. Optional native thinking configuration through ADK `BuiltInPlanner`.
7. Optional native ADK event compaction with a structured summarizer.
8. Caller-supplied ADK app plugins.
9. Optional native ADK structured user elicitation and resumability.
10. A stable elicitation request projection and response helper for clients.
11. An explicit model catalog injected into root-agent context when spawning is enabled.
12. Validated per-spawn model selection.

## Phase 1 Scope

| Capability | Output |
| --- | --- |
| Agent factory | `create_deep_agent(...) -> google.adk.apps.App` |
| Root agent | ADK `LlmAgent` assembled inside the factory |
| Task ledger | One `todo` function tool |
| Task state | Ledger stored through `ToolContext.state` |
| Active-ledger context | Root `LlmAgent.before_model_callback` injection |
| Skills | `skills` argument accepting one developer-created ADK `SkillToolset` |
| Thinking | `thinking` factory option mapped to ADK `BuiltInPlanner` |
| Compaction | `EventsCompactionConfig` plus structured summarizer |
| Plugin extension | User-supplied `BasePlugin` values passed into `App.plugins` |
| Testing | Unit and integration coverage for the configured behaviors |

## Public API

### Factory Signature

```python
from collections.abc import Sequence

from google.adk.agents.llm_agent import ToolUnion
from google.adk.apps import App
from google.adk.models import BaseLlm
from google.adk.plugins import BasePlugin
from google.adk.tools.skill_toolset import SkillToolset


def create_deep_agent(
    *,
    name: str,
    model_client: str | BaseLlm,
    instruction: str,
    description: str = "",
    tools: Sequence[ToolUnion] = (),
    skills: SkillToolset | None = None,
    thinking: bool | ThinkingConfig = False,
    compaction: CompactionConfig | None = None,
    plugins: Sequence[BasePlugin] = (),
    subagents: Sequence[SubAgentSpec] = (),
    spawn: SpawnConfig | None = None,
    elicitation: bool = False,
    available_models: Sequence[str | ModelSpec] = (),
) -> App:
    ...
```

### Configuration Models

```python
class ThinkingConfig(BaseModel):
    enabled: bool = True
    include_thoughts: bool = False
    thinking_budget: int | None = None


class CompactionConfig(BaseModel):
    token_threshold: int
    event_retention_size: int = 20
    compaction_interval: int = 999
    overlap_size: int = 0
```

### Factory Contract

| Input | Factory behavior |
| --- | --- |
| `model_client` | Forward unchanged to `LlmAgent.model`; accepts a model name or ADK `BaseLlm` model client |
| `instruction` | Use as base agent instruction and append the built-in ledger tool guidance |
| `tools` | Add directly to the root agent and append the built-in `todo` tool; accepts ADK `ToolUnion` values |
| `skills` | Append one developer-created `SkillToolset` to root agent tools when supplied |
| `thinking=False` | Do not install an ADK planner |
| `thinking=True` | Install `BuiltInPlanner(types.ThinkingConfig())` |
| `thinking=ThinkingConfig(...)` | Install `BuiltInPlanner` with supplied enabled configuration |
| `compaction=None` | Do not configure native event compaction |
| `compaction=CompactionConfig(...)` | Build native `EventsCompactionConfig` and summarizer |
| `plugins` | Pass into `App.plugins` unchanged |
| `elicitation=True` | Attach ADK `request_input`, append schema guidance, and enable resumability |
| `available_models` | Build the model registry used by root context and spawned-agent validation |

### Tools Input

The `tools` argument accepts ADK `ToolUnion` values:

| Tool input | Examples |
| --- | --- |
| Plain callable | Python function that ADK wraps as `FunctionTool` |
| `BaseTool` | `FunctionTool`, `LongRunningFunctionTool`, `AgentTool`, built-in ADK tools |
| `BaseToolset` | `McpToolset`, Google API toolsets, Toolbox toolsets, other ADK toolsets |

MCP tools are passed through as `McpToolset` values in `tools`. The factory
does not need a separate MCP-specific argument.

## Factory Assembly

```text
create_deep_agent(...)
  |
  |-- create built-in todo function tool
  |-- create built-in active-ledger before_model_callback
  |-- append supplied ADK SkillToolset to agent tools when supplied
  |-- normalize ThinkingConfig
  |-- create BuiltInPlanner when thinking is enabled
  |-- create structured event summarizer when compaction is enabled
  |-- create EventsCompactionConfig when compaction is enabled
  |-- create LlmAgent(
  |     name,
  |     model_client,
  |     instruction,
  |     description,
  |     tools,
  |     planner,
  |     before_model_callback,
  |   )
  `-- return App(
        name=name,
        root_agent=root_agent,
        plugins=list(plugins),
        events_compaction_config=events_compaction_config,
      )
```

## ADK Primitive Mapping

| Implementation need | ADK primitive |
| --- | --- |
| Root model-driven agent | `google.adk.agents.LlmAgent` |
| App container | `google.adk.apps.App` |
| Invocation runtime | `google.adk.runners.Runner` used by the caller |
| Todo tool | ADK function tool using `ToolContext` |
| Durable session ledger state | `ToolContext.state` and `CallbackContext.state` |
| Active ledger injection | `LlmAgent.before_model_callback` |
| Agent skills | `google.adk.tools.skill_toolset.SkillToolset` |
| Model thinking | `google.adk.planners.BuiltInPlanner` with `google.genai.types.ThinkingConfig` |
| Event compaction config | `google.adk.apps._configs.EventsCompactionConfig` |
| Summary implementation | `BaseEventsSummarizer` or configured `LlmEventSummarizer` |
| Global user extensions | `App.plugins` using `BasePlugin` |

## Skills Attachment

### Factory Input

The `skills` argument accepts one ADK `SkillToolset` already constructed by the developer. A developer combines all inline or filesystem skills needed by the agent inside that toolset:

```python
skills: SkillToolset | None = None
```

The factory does not construct ADK `Skill` objects or configure skill registries. It adds the supplied toolset to the root agent tools when present:

```python
root_tools = [*tools]
if skills is not None:
    root_tools.append(skills)
root_tools.append(todo_tool)
```

### Inline Skills Usage

```python
from google.adk.skills import models
from google.adk.tools import skill_toolset

greeting_skill = models.Skill(
    frontmatter=models.Frontmatter(
        name="greeting-skill",
        description="Greet a person in a friendly manner.",
    ),
    instructions="Return a friendly greeting for the requested person.",
)

project_skills = skill_toolset.SkillToolset(
    skills=[greeting_skill],
)

app = create_deep_agent(
    name="assistant",
    model_client=model_client,
    instruction="Assist the user and load useful skills when relevant.",
    skills=project_skills,
)
```

### Filesystem Skills Usage

```python
import pathlib

from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

weather_skill = load_skill_from_dir(
    pathlib.Path(__file__).parent / "skills" / "weather-skill"
)

project_skills = skill_toolset.SkillToolset(
    skills=[weather_skill],
    additional_tools=[get_weather_tool],
)

app = create_deep_agent(
    name="assistant",
    model_client=model_client,
    instruction="Use skills when useful.",
    skills=project_skills,
)
```

### Skills Constraints

1. Accept one already-created ADK `SkillToolset` value through `skills`.
2. Keep ordinary caller tools and the supplied skill toolset in the same ADK root-agent tool list.
3. Do not wrap, clone, or mutate the supplied skill toolset.
4. Combine multiple skills inside the developer-owned `SkillToolset`, not by passing multiple toolsets.
5. Allow ADK `SkillToolset` to manage its skill activation state and dynamic tools.

## Task Ledger Implementation

### Data Models

```python
class TaskLedgerItem(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]


class TaskLedgerSummary(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int
    cancelled: int


class TaskLedgerResult(BaseModel):
    todos: list[TaskLedgerItem]
    summary: TaskLedgerSummary
```

### State Storage

The `todo` tool writes ledger content to:

```python
tool_context.state[LEDGER_STATE_KEY]
```

Default key:

```python
"adk_deep_agent:todos"
```

Built-in policy constants:

```python
LEDGER_STATE_KEY = "adk_deep_agent:todos"
MAX_LEDGER_ITEMS = 100
ENFORCE_SINGLE_IN_PROGRESS = True
REJECT_MULTIPLE_WRITES_PER_MODEL_TURN = True
```

The root callback reads the same key through:

```python
callback_context.state[LEDGER_STATE_KEY]
```

### Tool Contract

```python
def todo(
    todos: list[TaskLedgerItem] | None = None,
    merge: bool = False,
    tool_context: ToolContext = ...,
) -> dict:
    ...
```

| Call | Operation |
| --- | --- |
| `todo()` | Return the full current ledger and summary counts |
| `todo(todos=[...])` | Replace the ordered ledger |
| `todo(todos=[...], merge=True)` | Update existing items by ID and append new items |

Example successful response:

```json
{
  "todos": [
    {"id": "1", "content": "Inspect inputs", "status": "completed"},
    {"id": "2", "content": "Prepare response", "status": "in_progress"}
  ],
  "summary": {
    "total": 2,
    "pending": 0,
    "in_progress": 1,
    "completed": 1,
    "cancelled": 0
  }
}
```

### Validation Rules

| Rule | Tool result on violation |
| --- | --- |
| Item ID must be a non-empty string | Validation error; state unchanged |
| Item content must be a non-empty string | Validation error; state unchanged |
| Status must be a declared value | Validation error; state unchanged |
| IDs in one write must be unique | Validation error; state unchanged |
| At most one item may be `in_progress` | Validation error; state unchanged |
| Item count must not exceed `MAX_LEDGER_ITEMS` | Validation error; state unchanged |
| More than one write call from one model turn | Tool error; state unchanged for competing writes |

### Added Root Instruction

Append the following built-in package instruction to the caller's instruction:

```text
You have a `todo` tool for tracking multi-step work. Use it for work with
multiple meaningful steps. Keep at most one item in progress, mark completed
items promptly, and keep the list concise.
```

## Active Ledger Injection Callback

### Callback Placement

Implement active-ledger injection as a `before_model_callback` attached only to the root `LlmAgent` created by `create_deep_agent(...)`.

Do not implement ledger injection as an `App` plugin in Phase 1.

### Callback Contract

```python
async def inject_active_ledger(
    *,
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    ...
```

### Callback Behavior

1. Read items from `callback_context.state[LEDGER_STATE_KEY]`.
2. Select items whose status is `pending` or `in_progress`.
3. Return `None` without modifying the request when no active items exist.
4. Format a compact active-ledger instruction.
5. Append the formatted text to the outgoing model request system instruction.
6. Return `None` so the normal ADK model call continues.

Injected format:

```text
[Active task ledger]
- [>] 2. Prepare response (in_progress)
- [ ] 3. Verify result (pending)
```

### Callback Composition

Phase 1 attaches the package callback to the root agent. User-supplied application-wide plugins remain in `App.plugins` and execute according to ADK plugin ordering.

## Thinking Configuration

### Planner Mapping

Use the ADK planner path for wrapper-managed thinking:

```python
from google.adk.planners import BuiltInPlanner
from google.genai import types

planner = BuiltInPlanner(
    thinking_config=types.ThinkingConfig(
        include_thoughts=config.include_thoughts,
        thinking_budget=config.thinking_budget,
    )
)
```

| Factory input | Root agent planner |
| --- | --- |
| `thinking=False` | `None` |
| `thinking=True` | `BuiltInPlanner(thinking_config=types.ThinkingConfig())` |
| `ThinkingConfig(enabled=False)` | `None` |
| `ThinkingConfig(enabled=True, ...)` | `BuiltInPlanner` with supplied values |

### Implementation Constraints

1. Configure wrapper-managed thinking only through `LlmAgent.planner`.
2. Do not set `generate_content_config.thinking_config` in factory logic.
3. Pass `include_thoughts` and `thinking_budget` to native ADK configuration unchanged.
4. Surface ADK/provider errors when the selected model does not support the requested thinking configuration.

## Compaction and Summarization

### Configuration Mapping

When compaction is supplied, create native ADK configuration:

```python
EventsCompactionConfig(
    summarizer=structured_summarizer,
    compaction_interval=config.compaction_interval,
    overlap_size=config.overlap_size,
    token_threshold=config.token_threshold,
    event_retention_size=config.event_retention_size,
)
```

### Structured Summary Contents

The Phase 1 summarizer prompt requests:

1. User goal and constraints.
2. Completed actions and results.
3. Changed files, resources, or generated outputs.
4. Outstanding issues.
5. Next intended action.

The summary does not store task-ledger state. Active ledger items remain in session state and are supplied by `inject_active_ledger`.

### Initial Supported Trigger

Implement and test token-threshold compaction. Keep `compaction_interval` and `overlap_size` present because they are required by the inspected ADK configuration class.

## Plugin Surface

Phase 1 does not use a package plugin for the task ledger.

The factory accepts:

```python
plugins: Sequence[BasePlugin] = ()
```

and passes these to:

```python
App(..., plugins=list(plugins))
```

This preserves ADK plugins for caller-owned global functionality such as logging, telemetry, global policy, or request processing.

## Proposed Package Files

```text
adk_deep_agent/
  __init__.py
  builder.py
  config.py
  ledger/
    __init__.py
    models.py
    tool.py
    callbacks.py
  compaction/
    __init__.py
    summarizer.py
tests/
  unit/
    test_builder.py
    test_skills_attachment.py
    test_thinking_config.py
    test_todo_tool.py
    test_ledger_callback.py
    test_compaction_config.py
  integration/
    test_deep_agent_task_ledger.py
    test_compaction_preserves_active_ledger.py
examples/
  phase1_task_ledger_agent.py
```

## Implementation Steps

### Step 1: Package and Configuration

1. Create the `adk_deep_agent` package and exports.
2. Implement `ThinkingConfig` and `CompactionConfig`.
3. Implement the initial `create_deep_agent(...)` signature.

### Step 2: Ledger Models and Tool

1. Implement ledger item, summary, and result models.
2. Implement the `todo` read, replace, and merge operations.
3. Read and write ledger state using `ToolContext.state`.
4. Implement validation, limits, and conflicting-write handling.

### Step 3: Skills Attachment

1. Add `skills: SkillToolset | None = None` to `create_deep_agent(...)`.
2. Append the supplied ADK skill toolset to the root `LlmAgent.tools` list when present.
3. Keep developer-owned `SkillToolset` configuration unchanged.
4. Add an example with an inline ADK skill.

### Step 4: Root Agent Context Injection

1. Implement `inject_active_ledger(...)` as an ADK `before_model_callback`.
2. Read active state through `CallbackContext.state`.
3. Append only active ledger items to the model request instruction.
4. Attach the callback to the constructed root `LlmAgent`.

### Step 5: Thinking

1. Normalize boolean and configured thinking inputs.
2. Build `BuiltInPlanner` only when thinking is enabled.
3. Supply the planner to the root `LlmAgent`.
4. Preserve native `include_thoughts` and `thinking_budget` values.

### Step 6: Compaction

1. Implement the structured event summarizer.
2. Translate `CompactionConfig` into `EventsCompactionConfig`.
3. Attach the native compaction configuration to `App`.
4. Verify task-ledger state is still injected after compacted context is used.

### Step 7: Factory Assembly

1. Append the built-in ledger instruction.
2. Combine caller tools, the optional ADK skill toolset, and the built-in `todo` tool.
3. Preserve caller-supplied `ToolUnion` values, including callables, `BaseTool` values, and `BaseToolset` values such as `McpToolset`.
4. Construct the root `LlmAgent`.
5. Construct and return the standard ADK `App`.
6. Pass caller plugins unchanged through `App.plugins`.

### Step 8: Tests and Example

1. Add unit tests for config normalization and factory assembly.
2. Add unit tests for todo reads, replaces, merges, validation, counts, and write conflicts.
3. Add unit tests for `SkillToolset` pass-through and root-agent tool composition.
4. Add unit tests for active-ledger callback formatting and request mutation.
5. Add unit tests for thinking disabled/enabled and planner field mapping.
6. Add unit tests for native compaction configuration mapping.
7. Add integration tests with an ADK runner and session service.
8. Add a Phase 1 usage example containing an inline skill toolset.

## Test Matrix

| Test area | Verification |
| --- | --- |
| Factory with defaults | Returns an `App` containing a root `LlmAgent`, `todo` tool, and no planner |
| ToolUnion tools | Callable tools, `BaseTool` values, and `BaseToolset` values are preserved in root-agent tools |
| Todo read/write | Writes state through `ToolContext.state` and returns expected summary |
| Todo merge | Updates by ID while retaining ledger order |
| Todo policy | Invalid and conflicting writes leave state unchanged |
| Skills omitted | Root agent has no skill toolset beyond caller ordinary tools and built-in `todo` |
| Skills supplied | Supplied `SkillToolset` object appears unchanged in root agent tools |
| Callback with no active items | Does not change request |
| Callback with active items | Adds compact active-ledger instruction before a model call |
| Same-run update visibility | A model call after `todo` uses updated active items |
| Thinking disabled | Root agent planner is `None` |
| Thinking enabled | Root agent planner is `BuiltInPlanner` |
| Thinking configured | Native thinking fields match caller configuration |
| Compaction mapping | App has native ADK event-compaction configuration |
| Continuity after compaction | Ledger remains in state and callback exposes active items |
| Plugins pass-through | Supplied plugins appear in `App.plugins` unchanged |

## Acceptance Criteria

| Capability | Completion condition |
| --- | --- |
| Factory | One function creates a standard ADK `App` and root `LlmAgent` |
| Model client and instruction | Caller values are supplied to the created root agent |
| Tools | Caller `ToolUnion` values are attached unchanged alongside the built-in `todo` tool |
| Task ledger | One `todo` tool stores and reads validated task state from ADK session state |
| Active context | Active items are injected through root `before_model_callback` before each relevant model request |
| Skills | One developer-created ADK `SkillToolset` can be passed in `skills` and is attached unchanged to root-agent tools |
| Thinking | Factory exposes off/default/configured modes mapped to `BuiltInPlanner` |
| Compaction | Factory supports native token-threshold event compaction with structured summarization |
| Plugin API | Caller plugins pass through as app-level ADK plugins |
| Tests | Unit and integration tests cover factory, skills, ledger, callback, thinking, and compaction behavior |
| Elicitation | Interruption projects to a UI request and resumes with the matching function response |
| Spawn model | Registered model IDs select their configured clients; unknown IDs are rejected |

## Phase 2 Plan: Subagents

Phase 2 adds focused subagent delegation while keeping the Phase 1 factory as the single public entry point.

### Phase 2 Scope

| Capability | Output |
| --- | --- |
| Prebuilt subagents | Developer-declared child agents attached through ADK `LlmAgent.sub_agents` |
| On-demand spawned subagents | Built-in `spawn_subagent` tool that creates a temporary ADK `LlmAgent` and runs it through `ToolContext.run_node(...)` |
| Subagent tools | Per-subagent `ToolUnion` lists selected by the developer |
| Subagent skills | Optional per-subagent ADK `SkillToolset` |
| Delegation modes | `single_turn` first, `task` as explicit opt-in |
| State sharing | Use ADK session state; child runs receive normal ADK context/state visibility |
| Stream visibility | Preserve native ADK runner events and add an SDK projection option |
| Background jobs | Out of Phase 2; handled by a later task-id based API |

### Public API Additions

```python
from typing import Literal

from pydantic import BaseModel


class SubAgentSpec(BaseModel):
    name: str
    goal: str
    instruction: str | None = None
    description: str = ""
    model_client: str | BaseLlm | None = None
    tools: Sequence[ToolUnion] = ()
    skills: SkillToolset | None = None
    mode: Literal["single_turn", "task"] = "single_turn"


class SpawnConfig(BaseModel):
    enabled: bool = False
    tools: Mapping[str, ToolUnion] = Field(default_factory=dict)
    skills: Mapping[str, SkillToolset] = Field(default_factory=dict)
    allowed_tools: Sequence[str] = ()
    allowed_skills: Sequence[str] = ()
    default_mode: Literal["single_turn", "task"] = "single_turn"
    stream_mode: Literal["events", "summary", "silent"] = "events"
    max_depth: int = 1
```

Extend the factory:

```python
def create_deep_agent(
    *,
    name: str,
    model_client: str | BaseLlm,
    instruction: str,
    description: str = "",
    tools: Sequence[ToolUnion] = (),
    skills: SkillToolset | None = None,
    thinking: bool | ThinkingConfig = False,
    compaction: CompactionConfig | None = None,
    plugins: Sequence[BasePlugin] = (),
    subagents: Sequence[SubAgentSpec] = (),
    spawn: SpawnConfig | None = None,
) -> App:
    ...
```

### Prebuilt Subagent Assembly

Prebuilt subagents use ADK's native static child-agent system:

```text
SubAgentSpec
  |
  |-- normalize model_client, defaulting to root model_client
  |-- combine spec.tools and optional spec.skills
  |-- create LlmAgent(
  |     name=spec.name,
  |     model=spec.model_client or root model_client,
  |     instruction=spec.instruction or generated instruction from spec.goal,
  |     description=spec.description or spec.goal,
  |     tools=child_tools,
  |     mode=spec.mode,
  |   )
  `-- attach child to root LlmAgent.sub_agents
```

ADK automatically exposes prebuilt child agents as delegation tools when they are present during root-agent construction:

| Child mode | ADK behavior |
| --- | --- |
| `single_turn` | ADK wraps the child with `_SingleTurnAgentTool`; the parent awaits the child result |
| `task` | ADK wraps the child with `_TaskAgentTool`; workflow dispatch runs the child with task isolation and waits/resumes |

Phase 2 should prefer `single_turn` for focused delegated work. Use `task` only when the child may need user clarification.

### On-Demand Spawn Tool

On-demand spawning does not mutate `root_agent.sub_agents` at runtime. Instead, Phase 2 adds a root tool:

```python
async def spawn_subagent(
    name: str,
    goal: str,
    context: str | None = None,
    tool_names: list[str] | None = None,
    skill_names: list[str] | None = None,
    mode: Literal["single_turn", "task"] | None = None,
    model: str | None = None,
    tool_context: ToolContext = ...,
) -> dict:
    ...
```

The tool behavior:

1. Validate the requested `name` as an ADK-compatible agent name.
2. Resolve requested tools and skills from developer-owned spawn registries.
3. Validate requested tools and skills against developer-owned allowlists.
4. Resolve `model` from the developer-owned model registry, defaulting to the root model.
5. Add only resolved allowed tools and skills to the temporary agent.
6. Use `mode or spawn.default_mode`.
7. Run the temporary child through:

```python
result = await tool_context.run_node(
    child_agent,
    node_input={
        "goal": goal,
        "context": context,
    },
    use_sub_branch=True,
)
```

8. Return a structured result to the parent model.

The spawned child is an ADK agent and uses ADK execution, but it is not registered as a static `sub_agents` entry.

For spawned `task` children, raw child clarification messages appear in the ADK
event stream. Because the spawned child is created inside a function-tool
wrapper rather than registered as a static task subagent, the next user turn is
not automatically routed back into that temporary child. If a spawned task
returns no `finish_task` output, the spawn tool returns `status:
"waiting_for_user"` with the last child message so the parent can continue the
interaction explicitly.

### Streaming Behavior

| Subagent type | Phase 2 stream source |
| --- | --- |
| Prebuilt `single_turn` | Native ADK runner events emitted while `_SingleTurnAgentTool` awaits `run_node(...)` |
| Prebuilt `task` | Native ADK task-isolation events and synthesized function responses |
| Spawned child | Events produced by `ToolContext.run_node(...)` for the dynamic child run |

Expose SDK-level stream projection without replacing ADK events:

```python
class SubagentEvent(BaseModel):
    parent_agent: str
    child_agent: str
    kind: Literal["start", "message", "tool_call", "tool_result", "complete", "error"]
    content: dict
```

`SpawnConfig.stream_mode` behavior:

| Mode | Behavior |
| --- | --- |
| `events` | Project child ADK events into package `SubagentEvent` objects when the caller uses the SDK stream helper |
| `summary` | Return only start/completion/result metadata |
| `silent` | Do not expose package-level child event projection; native ADK events still exist in the runner stream |

### State Behavior

1. Use ADK session state as the shared state layer.
2. Keep the root task ledger in the same session state key from Phase 1.
3. Allow child agents to read session state normally through ADK contexts.
4. Do not give spawned children write access to package registries or root configuration.
5. Add child-output metadata under package-owned state keys only if needed for streaming/result correlation.

### Guardrails

| Area | Phase 2 rule |
| --- | --- |
| Tool access | Spawned agents can only use tools selected from developer-provided allowlists |
| Skill access | Spawned agents can only use skills selected from developer-provided allowlists |
| Recursion | Spawned agents do not receive `spawn_subagent` by default |
| Mode | Default spawned mode is `single_turn` |
| Names | Validate names with ADK agent naming rules and avoid collisions with existing prebuilt child names |
| Background work | Do not return task IDs or keep spawned children running after the tool call in Phase 2 |

### Phase 2 Implementation Steps

1. Add `SubAgentSpec` and `SpawnConfig`.
2. Extend `create_deep_agent(...)` with `subagents` and `spawn`.
3. Build prebuilt child `LlmAgent` instances before root `LlmAgent` construction.
4. Pass prebuilt children through `root_agent.sub_agents`.
5. Add `spawn_subagent` only when `spawn.enabled` is true.
6. Implement developer-owned tool and skill registries for spawned children through `SpawnConfig.tools` and `SpawnConfig.skills`.
7. Implement dynamic child construction and `ToolContext.run_node(...)` execution.
8. Add subagent event projection helpers for native ADK runner events.
9. Add examples for one prebuilt `single_turn` child and one on-demand spawned child.
10. Add tests for prebuilt assembly, spawn validation, allowed tools/skills, state visibility, and stream projection.

### Phase 2 Acceptance Criteria

| Capability | Completion condition |
| --- | --- |
| Prebuilt child | A `SubAgentSpec` creates an ADK child agent available to the root agent as native ADK delegation |
| Single-turn delegation | Root agent can call a prebuilt `single_turn` child and receive a result |
| Task delegation | Root agent can call an explicitly configured `task` child and resume after completion or user wait |
| Spawn tool | Root agent receives `spawn_subagent` only when spawn is enabled |
| Spawn validation | Unknown tools, unknown skills, invalid names, and disallowed recursion are rejected |
| Model validation | Unknown model IDs are rejected before child construction |
| Dynamic execution | Spawned child runs through `ToolContext.run_node(...)` and returns a structured result |
| Spawned task wait | Spawned task children that ask the user return `waiting_for_user` rather than `completed` |
| State | Root and child can access shared session state while package-owned config remains protected |
| Streaming | SDK helper can project child start/tool/result/complete events from native ADK runner events |
| Tests | Unit and integration tests cover prebuilt and spawned subagent paths |

## Implemented Addition: Elicitation and Model Selection

The factory now accepts:

```python
def create_deep_agent(
    ...,
    elicitation: bool = False,
    available_models: Sequence[str | ModelSpec] = (),
) -> App:
    ...
```

`elicitation=True` attaches ADK's native `request_input` tool and creates a
resumable `App`. `project_elicitation_event(...)` exposes the message, response
schema, call ID, author, and invocation ID. `create_elicitation_response(...)`
returns the matching user-role function response expected by `Runner`.

`ModelSpec` separates the public model ID and descriptive context from the
backend `str | BaseLlm` client. The generated root instruction contains the
allowed catalog when spawning is enabled. The spawn tool accepts an optional
`model` argument, resolves it through that registry, reports the selected ID in
its result, and rejects unknown values.

Acceptance coverage includes:

1. No second model call before an elicitation response is supplied.
2. Structured object answers resume the same invocation.
3. Elicitation remains opt-in and enables resumability.
4. Spawned children execute with the selected registered model client.
5. Unknown model IDs return a structured spawn error.

## ADK Source References

| Implementation area | Source |
| --- | --- |
| `LlmAgent`, callbacks, planner field | [`adk-python/src/google/adk/agents/llm_agent.py`](adk-python/src/google/adk/agents/llm_agent.py) |
| Session state in tool context | [`adk-python/src/google/adk/tools/tool_context.py`](adk-python/src/google/adk/tools/tool_context.py), [`adk-python/src/google/adk/agents/context.py`](adk-python/src/google/adk/agents/context.py) |
| Per-model callback execution | [`adk-python/src/google/adk/flows/llm_flows/base_llm_flow.py`](adk-python/src/google/adk/flows/llm_flows/base_llm_flow.py) |
| Native skill toolsets | [`adk-python/src/google/adk/tools/skill_toolset.py`](adk-python/src/google/adk/tools/skill_toolset.py), [ADK skills documentation](https://adk.dev/skills/#inline-skills) |
| Built-in thinking planner | [`adk-python/src/google/adk/planners/built_in_planner.py`](adk-python/src/google/adk/planners/built_in_planner.py) |
| App plugin surface | [`adk-python/src/google/adk/plugins/base_plugin.py`](adk-python/src/google/adk/plugins/base_plugin.py), [`adk-python/src/google/adk/apps/app.py`](adk-python/src/google/adk/apps/app.py) |
| Compaction configuration and execution | [`adk-python/src/google/adk/apps/_configs.py`](adk-python/src/google/adk/apps/_configs.py), [`adk-python/src/google/adk/apps/compaction.py`](adk-python/src/google/adk/apps/compaction.py) |
| Static subagent declaration and mode wrapping | [`adk-python/src/google/adk/agents/base_agent.py`](adk-python/src/google/adk/agents/base_agent.py), [`adk-python/src/google/adk/agents/llm_agent.py`](adk-python/src/google/adk/agents/llm_agent.py) |
| Native single-turn and task subagent tools | [`adk-python/src/google/adk/tools/agent_tool.py`](adk-python/src/google/adk/tools/agent_tool.py) |
| Dynamic child execution | [`adk-python/src/google/adk/agents/context.py`](adk-python/src/google/adk/agents/context.py), [`adk-python/src/google/adk/workflow/_llm_agent_wrapper.py`](adk-python/src/google/adk/workflow/_llm_agent_wrapper.py) |

# ADK Deep Agent: Conceptual Design and Pattern Selection

Status: Living design; core, subagent, elicitation, and model-selection phases implemented
Target package: `adk-deep-agent`  
Python package: `adk_deep_agent`  
Updated: 2026-07-12

## Purpose

This document defines the conceptual design for an opinionated deep-agent
package built on Google ADK. It compares relevant behavior in:

1. LangChain Deep Agents, referred to below as Deep Agents.
2. Hermes Agent, referred to below as Hermes.
3. Google ADK, as the runtime foundation for `adk-deep-agent`.

For each capability, the document answers:

1. How does Deep Agents implement the capability?
2. How does Hermes implement the capability?
3. What native ADK primitive is available?
4. Which pattern should `adk-deep-agent` adopt?

This is not an implementation checklist. The ADK-specific Phase 1 build plan
belongs in `ADK-DEEP-AGENT-IMPLEMENTATION-PLAN.md`.

## Source Basis

The comparisons below are grounded in the locally cloned source trees:

| Project | Source areas inspected | Relevant concepts |
| --- | --- | --- |
| Deep Agents | `deepagents/libs/deepagents/deepagents/graph.py`, `profiles/harness/_openai_codex.py`, `middleware/subagents.py`, `middleware/async_subagents.py`, `middleware/summarization.py`, `_subagent_transformer.py`, `middleware/skills.py` | Builder facade, middleware, planning guidance, todos, delegated tasks, background tasks, typed subagent streams, compaction, skills |
| Hermes | `hermes-agent/run_agent.py`, `agent/conversation_loop.py`, `tools/todo_tool.py`, `tools/delegate_tool.py`, `agent/conversation_compression.py`, `agent/shell_hooks.py`, `agent/prompt_builder.py` | Owned agent loop, compact todo tool, child execution controls, progress relays, compaction continuity, hooks, skills |
| Google ADK | `adk-python/src/google/adk/apps`, `agents/llm_agent.py`, `agents/llm/task`, `flows/llm_flows`, `plugins`, `tools/skill_toolset.py`, `planners` | `App`, `Runner`, native agents, task modes, events, callbacks/plugins, compaction, skills, thinking |

## Design Position

`adk-deep-agent` should be an opinionated assembly layer over ADK, not a new
agent runtime.

The package should provide a small builder API that assembles an ordinary ADK
`App` with an internal root `LlmAgent`, selected built-in features, and
developer extensions. ADK must remain responsible for execution, sessions,
events, model calls, tools, and application lifecycle.

The guiding hybrid is:

| Source | Pattern to adopt |
| --- | --- |
| Deep Agents | A single convenience factory and a coherent default feature bundle |
| Hermes | Compact operational tools, visible progress, context-continuity behavior, and guarded child execution |
| Google ADK | Native runtime, state, callbacks, plugins, compaction, skill toolsets, planners, and future task-agent execution |

## Capability Summary

| Capability | Deep Agents | Hermes | ADK direction |
| --- | --- | --- | --- |
| Agent loop | LangGraph agent assembled with middleware | Custom `AIAgent` loop | Use native `App` plus `Runner`; build no loop |
| Planning | Explicit task-plan updates through built-in `write_todos` and instruction guidance | Explicit task-plan updates through compact `todo` tool; reasoning is separate | Use built-in todo ledger for external planning; keep native thinking separate |
| Todo tracking | `TodoListMiddleware` with `write_todos` | Single compact `todo` tool | Built-in `todo` tool stored in ADK session state |
| Subagent delegation | Ephemeral `task` subgraphs | Blocking `delegate_task` children | Native implemented `single_turn`/`task` children |
| Background subagents | Remote Agent Protocol task tools | No equivalent durable job contract found | Separate future service, potentially A2A backed |
| Subagent streaming | Typed child run streams | Progress callback relay and live tree status | Project ADK `Event` data without replacing it |
| Context compaction | Summarization middleware and compact tool | Custom compressor with todo reinjection | Native app event compaction plus ledger reinjection |
| Hooks | LangChain middleware | Python and shell hooks | Agent callbacks for local behavior; plugins for global behavior |
| Skills | Middleware over skill sources | Prompt-indexed skill catalog and skill tools | Accept one developer-created ADK `SkillToolset` |
| Thinking | Model/middleware dependent | Provider reasoning configuration | Native ADK `BuiltInPlanner` configuration |
| Structured elicitation | Interrupt/approval middleware | Blocking `clarify` callback with UI request/response IDs | Native ADK `request_input`, resumable invocation, and matching `FunctionResponse` |
| Spawn model selection | Model profiles supplied to delegated agents | Child model/provider configuration | Explicit validated model registry exposed as instruction context |

## 1. Agent Loop and Runtime Ownership

### Deep Agents Pattern

Deep Agents exposes `create_deep_agent(...)`, but its returned object is a
compiled LangGraph/LangChain agent. The builder assembles a middleware stack
around `create_agent(...)`. The default stack includes planning/todos,
filesystem capabilities, subagents, summarization, and tool-call patching;
skills, asynchronous subagents, memory, and human-in-the-loop behavior are
attached conditionally.

The important architectural property is that product behavior is expressed as
middleware layered into the underlying agent graph.

### Hermes Pattern

Hermes owns its runtime loop through `AIAgent`. It constructs provider calls,
executes tool calls, coordinates streaming callbacks, invokes compression, and
dispatches delegated children itself. Its tools and hooks are designed around
that owned loop.

The important architectural property is that Hermes can apply operational
policies directly because it controls the execution loop.

### ADK Native Fit

ADK already owns the equivalent runtime concerns:

| Concern | ADK primitive |
| --- | --- |
| Top-level application | `App` |
| Execution | `Runner` and `Runner.run_async(...)` |
| Root model agent | `LlmAgent` |
| Session history and state | ADK sessions |
| Tool and model boundaries | Agent callbacks and app plugins |
| Output progression | ADK events |

### ADK-Deep-Agent Recommendation

Adopt the Deep Agents facade idea, but not its middleware runtime model. Expose
`create_deep_agent(...) -> App` and construct a standard root `LlmAgent`
internally. Do not port the Hermes conversation loop, introduce a LangGraph
dependency, or wrap ADK in a second executor.

Phase 1 should be a configured ADK app with built-in ledger behavior, optional
thinking, optional compaction, one optional skill toolset, and user plugins.

## 2. Planning and Execution Tracking

### What Planning Means Here

For a deep agent, planning has two distinct layers:

| Layer | Meaning |
| --- | --- |
| Externalized task plan | A durable, inspectable list of work items and progress that the model updates through a tool |
| Internal model reasoning | Hidden or surfaced model thinking used to select the next action |

Deep Agents and Hermes primarily productize the first layer. ADK also
provides a native control for the second layer.

### Deep Agents Pattern

Deep Agents describes planning as part of its default product surface, but in
the inspected implementation it is supplied through `TodoListMiddleware` and
the built-in `write_todos` tool rather than a separate planner runtime. Its
model guidance asks agents to gather context, plan, implement, verify, and
reconcile todo or plan items before completion. The model creates and updates
the explicit plan while the graph and middleware persist it.

This gives planning an observable representation: plan progress appears as
todo state, and middleware can enforce safe updates.

### Hermes Pattern

Hermes' `todo_tool.py` identifies its tool as "Planning & Task Management."
The agent creates an ordered plan with the single `todo` tool, communicates
progress through item statuses, and restores active plan context after
compression. Hermes also supports provider reasoning settings, but those
configure model deliberation; they are not a separate user-visible planning
engine.

This makes planning compact and operational: the plan is the ledger the user
and agent can inspect, update, and resume.

### ADK Native Fit

ADK provides useful primitives for the two different layers:

| Need | ADK primitive |
| --- | --- |
| Durable visible work plan | Custom function tool plus session state and callback injection |
| Model internal thinking or reasoning | `BuiltInPlanner` with `ThinkingConfig` |
| Prompted plan/reason/act style | `PlanReActPlanner`, if intentionally selected in a later design |

The todo ledger and model thinking must not be treated as the same feature. A
thinking-enabled model may reason better without maintaining an external plan;
a ledger-enabled agent can track work even with thinking disabled.

### ADK-Deep-Agent Recommendation

Adopt the planning pattern shared by Deep Agents and Hermes: planning is
represented by the built-in `todo` ledger and is available by default in the
deep-agent surface.

1. The ledger is the explicit, persistent plan visible across turns and
   compaction.
2. `BuiltInPlanner` is optional model reasoning support, not the source of
   task state.
3. Do not add a separate public `planner` or `planning` argument in Phase 1.
4. Evaluate `PlanReActPlanner` only later as an optional alternate mode,
   because it changes prompting behavior and is not required for task-ledger
   planning.

## 3. Todo Tracking and Task Ledger

### Deep Agents Pattern

Deep Agents includes LangChain `TodoListMiddleware` by default. It exposes a
`write_todos` tool and stores todos in graph state. A notable safety behavior
is that if the model emits more than one `write_todos` call in the same model
message, all competing writes are rejected. This prevents parallel tool
execution from creating a nondeterministic plan.

This design is middleware-oriented: todo state and tool behavior belong to an
agent middleware feature.

### Hermes Pattern

Hermes uses a single `todo` tool with a compact contract:

| Operation | Behavior |
| --- | --- |
| `todo()` | Read the current full list |
| `todo(todos=[...])` | Replace the plan |
| `todo(todos=[...], merge=True)` | Update items by ID and append new items |

Items contain `id`, `content`, and `status`, with list order acting as
priority. The tool response includes the complete list and summary counts.
Hermes stores the list on the session's `AIAgent` instance. After conversation
compression, it injects only `pending` and `in_progress` items into the new
context, avoiding accidental repetition of completed work.

This design is payload-efficient and makes continuity after compaction
explicit.

### ADK Native Fit

ADK supplies session state and callback context, but not an opinionated todo
ledger. A function tool can write validated data through `ToolContext.state`.
A root-agent `before_model_callback` can read current ledger state before every
model request and append concise active-task context.

ADK may execute multiple tool calls from one model response concurrently.
Therefore, Deep Agents' reject-all competing-write behavior cannot be enforced
reliably only inside the `todo` tool. The model response must be examined
before competing todo tool calls are dispatched.

### ADK-Deep-Agent Recommendation

Use the Hermes tool surface and the Deep Agents safety behavior:

1. Provide one built-in `todo` tool; it is not an optional factory argument.
2. Store validated ledger state under an `adk_deep_agent:` namespaced session
   state key.
3. Expose read, replace, and merge behavior through the one compact tool.
4. Inject active items through a root `LlmAgent.before_model_callback`, not an
   application-wide plugin.
5. Add a root model-response guard for multiple todo writes so competing
   writes are rejected before ADK runs them in parallel.

The ledger remains authoritative in session state. Compaction summaries may
mention work, but they must not replace current task state.

## 4. Subagent Spawning and Delegation

### Terms

Delegation can mean different things:

| Form | Meaning |
| --- | --- |
| Transfer | Another conversational agent becomes responsible for responding |
| Focused delegated task | A child works in isolated context and returns a result to the parent |
| Background delegated job | A task continues independently after the parent turn returns |

The deep-agent use case primarily needs focused delegated tasks first, then
background jobs as a separate capability.

### Deep Agents Pattern

Deep Agents adds a `task` tool through `SubAgentMiddleware`. The parent selects
a named subagent and passes a detailed assignment. For each invocation, the
child receives a fresh messages state containing that assignment, performs its
work, and returns either a structured response or its final assistant text as
a tool result to the parent.

The parent does not receive the child's full intermediate context. The tool
description explicitly encourages multiple independent `task` calls in one
model message for concurrent work.

Subagents can be configured with their own model, tools, middleware, skills,
permissions, human-in-the-loop rules, and structured output format.

### Hermes Pattern

Hermes exposes `delegate_task`. It creates fresh child `AIAgent` instances
with focused prompts, restricted tools, and isolated working context. A single
delegation blocks until the child finishes. A batch request runs children in a
thread pool and returns results after all selected child work completes.

Hermes makes operational policy first-class:

| Policy | Behavior |
| --- | --- |
| Tool restrictions | Children do not receive dangerous or inappropriate parent tools by default |
| Recursion | Children are leaves by default; an explicit orchestrator role may delegate within depth limits |
| Concurrency | Maximum concurrent children is enforced |
| Timeout and stale work | Child timeouts and heartbeat tracking are applied |
| Cancellation | Active child registry supports interruption |
| Parent context | Parent receives summaries, not child working history |

### ADK Native Fit

The inspected ADK source supports three `LlmAgent` modes:

| Mode | Meaning |
| --- | --- |
| `chat` | Conversational agent available through transfer behavior |
| `single_turn` | Child completes an assigned task without chatting with the user |
| `task` | Child may interact to accomplish a task and completes through native `finish_task` behavior |

ADK has two useful subagent primitives, not one:

| Primitive | Use |
| --- | --- |
| Static `LlmAgent.sub_agents` | Prebuilt child agents declared by the developer before the root agent is constructed |
| `ToolContext.run_node(...)` | Dynamic execution of a temporary child agent or node at runtime |

When `single_turn` or `task` children are attached through
`LlmAgent.sub_agents`, ADK adds native child tools for them during root-agent
assembly. A `single_turn` child is exposed through ADK's internal
single-turn agent tool. A `task` child is exposed through ADK's internal
task-delegation marker and completed through `finish_task`.

For dynamic spawned children, mutating `root_agent.sub_agents` during a run is
not the right abstraction. The current model call will not automatically gain a
new clean delegation tool, and task-mode delegation expects the target to be
discoverable through the static root tree. Instead, an ADK-deep-agent spawn
tool should create a temporary `LlmAgent` and execute it with
`ToolContext.run_node(...)`.

This gives ADK-deep-agent two aligned paths:

| Subagent type | ADK primitive | Product behavior |
| --- | --- | --- |
| Prebuilt worker | `root_agent.sub_agents` | Named developer-defined workers such as researcher, reviewer, coder |
| On-demand worker | Built-in spawn/delegate tool plus `ToolContext.run_node(...)` | Hermes-like custom child with name, goal, context, and tools/skills selected from developer-owned registries |

ADK also scopes child execution through branch, node path, and task-isolation
metadata depending on the mode. This is much closer to delegated-task semantics
than ordinary conversational transfer.

There is one important distinction for interactive tasks. Static prebuilt
`task` subagents participate in ADK's task-isolation and resume flow. Dynamic
spawned `task` agents run through a function-tool wrapper; they can stream a
clarification message, but the next user turn is not automatically routed back
to that temporary child. ADK-deep-agent should surface that case as a
`waiting_for_user` spawn result and let the parent continue explicitly.

### ADK-Deep-Agent Recommendation

When subagents are added after the Phase 1 core:

1. Use native ADK `sub_agents` for prebuilt developer-declared workers.
2. Use an ADK-deep-agent spawn/delegate tool for on-demand workers, backed by
   `ToolContext.run_node(...)` and developer-owned tool/skill registries.
3. Default both paths to `single_turn` for focused non-interactive work.
4. Offer native ADK `task` as an explicit interactive delegated-task option
   for prebuilt subagents, and as a foreground spawned task that can report
   `waiting_for_user` when it needs clarification.
5. Do not implement focused work through conversational transfer.
6. Apply Hermes-style child tool restrictions, non-recursive defaults, depth
   limits, timeout policy, and cancellation policy around ADK child execution.
7. Preserve ADK-native result and task-completion behavior instead of defining
   a custom child runner.

This differs from Hermes in an important way: Hermes owns the child execution
loop and therefore must build progress relays, child registries, and result
plumbing itself. ADK-deep-agent should keep Hermes' operational guardrails but
use ADK's native agent execution, session, event, and task primitives.

It also differs from Deep Agents: Deep Agents productizes delegation as a
LangGraph/LangChain middleware tool. ADK-deep-agent should productize the same
developer experience but map it onto ADK's `sub_agents` and `run_node`
primitives.

Because these ADK task modes are newer capabilities in the cloned source, the
package should pin and compatibility-test the minimum ADK version before
making them public API promises.

## 5. Subagent Streaming and Progress Visibility

### Deep Agents Pattern

Deep Agents streams nested work through its graph streaming system. Its
`SubagentTransformer` identifies declared `task` executions and exposes typed
child stream handles. A consumer can observe a named child's message stream,
tool calls, completion state, task input, and the parent tool call that caused
the child run.

This gives consumers detailed nested execution visibility while the parent
still receives only a final task result for its own reasoning.

### Hermes Pattern

Hermes does not expose the child's full model context to its parent. Instead,
it relays operational progress through callbacks:

| Signal | Example use |
| --- | --- |
| Child start and completion | Render a delegated work tree |
| Thinking/progress events | Show that a child is active |
| Tool start information | Show current operation and previews |
| Identity fields | Attribute events to a child, parent, and depth |
| Interrupt/status registry | Enable control of live children |

Hermes streaming is therefore primarily a user-interface and control-plane
view over child work; final summaries remain the parent-facing result.

### ADK Native Fit

ADK yields raw `Event` objects during execution, including agent messages,
function calls, function responses, outputs, branch data, and node path data.
Local validation against the cloned ADK source and a probe run confirmed that
raw child events appear in the normal `Runner.run_async(...)` stream for all
Phase 2 subagent shapes:

| Shape | Raw ADK child events in outer runner stream |
| --- | --- |
| Prebuilt `single_turn` child through `sub_agents` | Yes |
| Prebuilt `task` child through `sub_agents` | Yes |
| On-demand `single_turn` child through `ToolContext.run_node(...)` | Yes |
| On-demand `task` child through `ToolContext.run_node(...)` | Yes |

The event metadata is not identical across modes:

| Mode | Useful raw fields |
| --- | --- |
| Prebuilt `single_turn` | Child `author`, child `node_info.path`, sub-branch, parent function response |
| Prebuilt `task` | Child `author`, child `node_info.path`, `finish_task` function call/response, task result output, synthesized parent-visible function response |
| Spawned `single_turn` | Spawned child `author`, spawned child `node_info.path`, sub-branch, spawn tool function response |
| Spawned `task` | Spawned child `author`, spawned child `node_info.path`, `finish_task` function call/response, spawn tool function response |

Therefore, ADK-deep-agent does not need to invent a separate internal streaming
engine. It can expose raw ADK events directly and optionally add a stable
projection for callers that want Deep Agents-style nested work visualization.

One caution: child detection should not rely only on `event.branch`.
Prebuilt task-mode child events may share the parent branch. A robust
projection should inspect `event.author`, `event.node_info.path`,
function-call/function-response names, configured child names, and package
spawn correlation metadata.

Reasoning/thought events should be treated as ordinary raw ADK content parts
when the selected model and thinking configuration emit them. Hidden reasoning
availability remains provider/model dependent.

### ADK-Deep-Agent Recommendation

Use ADK events as the sole execution stream. Do not create an independent
subagent event engine.

For a later subagent release, provide an optional projection layer that:

1. Classifies root output, child start, child output, child tool activity, and
   child completion.
2. Retains the raw ADK event for callers needing complete detail.
3. Uses public event metadata, configured child identities, and package-owned
   spawn correlation metadata.
4. Does not make private isolation fields part of the package's stable API.

The desirable product behavior is Deep Agents-style nested visibility with
Hermes-style compact progress presentation, carried over raw ADK events.

## 6. Synchronous, Asynchronous, and Background Subagents

### The Important Distinction

The word `async` covers several different capabilities:

| Capability | Parent waits for child result in the same logical request? | Example |
| --- | --- | --- |
| Async Python invocation | Yes | `await runner.run_async(...)` |
| Concurrent delegated calls | Yes, before final parent result | Several focused workers launched together |
| Background delegated job | No | Start now, return a task ID, check later |

These should not share one vague `async_subagent` design.

### Deep Agents Pattern

For focused synchronous subagents, the `task` tool has both sync and async
Python implementations and waits for the selected child result.

Separately, `AsyncSubAgentMiddleware` represents true background work on
remote Agent Protocol servers. It exposes five tools:

| Tool | Purpose |
| --- | --- |
| `start_async_task` | Start remote work and immediately return a task ID |
| `check_async_task` | Fetch live status and completed output |
| `update_async_task` | Send new instructions on the same remote thread |
| `cancel_async_task` | Cancel a running task |
| `list_async_tasks` | Refresh the set of known task statuses |

Task records are tracked in agent state, while execution belongs to the remote
server. Its prompt explicitly prevents busy polling and warns that stored
status may be stale.

### Hermes Pattern

Hermes supports parallel child execution inside one blocking
`delegate_task` call and exposes progress and interruption for those active
children. It does not provide the same persisted start/check/update/cancel
background-job contract in the inspected delegation implementation.

### ADK Native Fit

ADK already supports asynchronous application execution through
`Runner.run_async(...)`; this is not background delegation. For remote or
durable asynchronous work, ADK has relevant building blocks, including A2A
agents and long-running/resumable behavior, but a deep-agent product contract
would still need durable job identity, authorization, status, cancellation,
idempotency, and resume handling.

### ADK-Deep-Agent Recommendation

Keep the concepts separate:

1. Do not build wrappers around ADK sync/async runner invocation merely to call
   them subagent features.
2. When focused subagents are added, allow ADK to run native child work through
   ordinary sync or async application invocation.
3. Treat true background subagents as a later feature with explicit
   `start/check/update/cancel/list` semantics inspired by Deep Agents.
4. Use an ADK-aligned remote executor, likely A2A-backed, only after its
   persistence and streaming contract has been validated.

Hermes' progress, cancellation, timeout, and concurrency controls are useful
policy ideas for both foreground and future background work.

## 7. Context Compaction and Long-Running Continuity

### Deep Agents Pattern

Deep Agents implements summarization as middleware. It can automatically
compact when context reaches configured thresholds and exposes a
`compact_conversation` tool for model-requested compaction. It can offload
evicted history to a backend and includes optimizations for truncating large
older tool arguments before full summarization.

### Hermes Pattern

Hermes runs its own context compressor within the conversation loop. It
supports automatic and manual compression, checks compression-model
feasibility, preserves session lineage across compressed continuation
sessions, warns about repeated compression, and resets caches whose source
context has been summarized away.

Its most relevant behavior for this package is simple: after compression,
Hermes reinjects active todo items independently of the generated summary.
That prevents the task plan from silently disappearing or from being replaced
by a lossy summary.

### ADK Native Fit

ADK provides application-level event compaction through
`EventsCompactionConfig` and event summarizer interfaces. The inspected ADK
configuration supports token-threshold compaction but requires
`compaction_interval` and `overlap_size` fields as well. At runtime,
token-threshold compaction is attempted first; interval-based compaction can
still occur later if its required interval is reached.

ADK state remains distinct from compacted event history. A task ledger stored
in session state can therefore be read again after old events have been
summarized.

### ADK-Deep-Agent Recommendation

Use native ADK event compaction, not custom middleware or a custom compressor.

The package should:

1. Provide a structured summary configuration for goal, completed work,
   important findings, changed artifacts, and unresolved issues.
2. Keep todo state out of the summary's source-of-truth role.
3. Inject current active todos from session state before subsequent root model
   calls.
4. Describe its initial mode accurately as token-threshold-first native ADK
   compaction with the required interval fallback fields.
5. Consider manual compaction and large tool-output trimming only after native
   compaction behavior is established.

## 8. Hooks, Middleware, Callbacks, and Plugins

### Deep Agents Pattern

Deep Agents composes features through LangChain middleware. Middleware can
alter model requests, supply tools, manage state, restrict tools, summarize
messages, and introduce human-in-the-loop pauses. This is the central
extensibility mechanism of its runtime.

### Hermes Pattern

Hermes has callbacks embedded in its owned loop plus a plugin-hook manager. It
also supports consent-controlled shell hooks registered into the same hook
system. Its hook points include model request/response activity, tool
blocking/transformation, session lifecycle, approval behavior, and subagent
completion.

### ADK Native Fit

ADK has two related extension levels:

| ADK surface | Scope | Correct use |
| --- | --- | --- |
| Agent callbacks | A particular `LlmAgent` | Behavior specific to the root deep agent or one child |
| `BasePlugin` in `App.plugins` | All agents in the app | Global logging, telemetry, policy, caching, or audit behavior |

ADK runs plugins before agent callbacks and permits short-circuiting. A plugin
used for root-only todo injection would therefore also risk applying the root
task context to future delegated children.

### ADK-Deep-Agent Recommendation

Do not reproduce a generic middleware layer.

Use:

1. Root-agent callbacks for built-in root behavior, including active todo
   injection and the competing-todo-write response guard.
2. `App.plugins` for developer-supplied global extensions such as telemetry,
   policy, audit logging, caching, and broad lifecycle observation.
3. Explicit future child callbacks only when a subagent-specific feature is
   required.

This keeps extension scope obvious and follows ADK's intended composition
model.

## 9. Skills and Progressive Instruction Loading

### Deep Agents Pattern

Deep Agents supplies `SkillsMiddleware`. It loads skills from configured
backend paths, merges skill sources with precedence, exposes metadata to the
prompt, and uses backend abstraction rather than assuming local filesystem
storage.

### Hermes Pattern

Hermes discovers `SKILL.md` files from local and configured external skill
directories, builds a compact prompt index, supports platform and disabled
skill filtering, and supplies skill-related tools for loading or managing
skill content. It treats skills as reusable workflow knowledge separate from
ordinary memory.

### ADK Native Fit

ADK has an experimental `SkillToolset` capability. A developer can build one
toolset containing inline or filesystem-loaded ADK skills and attach it as one
agent toolset. ADK then owns the skill activation and dynamic tool behavior.

### ADK-Deep-Agent Recommendation

Expose the ADK primitive rather than building a second skill catalog in Phase
1:

```python
skills: SkillToolset | None = None
```

The caller constructs one `SkillToolset` containing any number of required
skills; the factory attaches it unchanged to the root agent. Accepting one
toolset avoids collisions among the standard tools exposed by multiple
toolsets and matches ADK's documented usage pattern.

Because this ADK feature is experimental, the package should declare its
minimum compatible ADK version and keep skills pass-through behavior covered
by compatibility tests.

## 10. Model Thinking and Reasoning

### Framework Comparison

The explicit task-plan behavior selected for this package is covered by the
todo ledger above. This section concerns internal model reasoning
configuration, not the durable external plan. Deep Agents can apply
model-profile thinking guidance; Hermes exposes provider-specific reasoning
behavior through its owned runtime. Neither requires reimplementing model
reasoning inside an ADK wrapper.

### ADK Native Fit

ADK exposes `BuiltInPlanner` with `google.genai.types.ThinkingConfig`.
Thinking behavior is model/provider-sensitive. In particular, a generic
enabled configuration without an explicit budget is not valid for every
supported `BaseLlm` adapter.

### ADK-Deep-Agent Recommendation

Expose explicit native thinking configuration and leave it off unless the
developer supplies it:

```python
thinking: ThinkingConfig | None = None
```

When supplied, translate it to `BuiltInPlanner`. Avoid a generic
`thinking=True` shorthand until provider-specific behavior is intentionally
defined and tested.

## 11. Structured Elicitation and Model-Aware Spawning

### Structured Elicitation

Use ADK's native `request_input` tool instead of introducing a package-owned
blocking callback or custom interruption runtime. The feature is opt-in because
clients must render the request and return a structured response.

When enabled, the package:

1. Attaches ADK's `request_input` long-running tool to the root agent.
2. Adds JSON Schema guidance for grouped questions, options, booleans,
   multi-select values, and required fields.
3. Enables ADK app resumability.
4. Projects the `adk_request_input` event into `ElicitationRequest` for UI code.
5. Builds the matching user-role `FunctionResponse` while retaining the
   original function-call and invocation IDs.

No model call runs while the request is waiting. The next model call happens
only after the client resumes the interrupted invocation.

### Model-Aware Spawning

ADK configures the root agent's model but does not automatically expose a
provider's complete model inventory to the LLM. Accept an explicit
`available_models` list and build one backend registry from it. Inject only
public IDs, descriptions, and capabilities into root instruction context.
Keep model clients and credentials in the backend registry.

`spawn_subagent` accepts an optional model ID, defaults to the root model, and
rejects IDs outside the registry. Context and execution therefore share the
same source of truth.

## 12. Guardrails and Additional Patterns

The comparison surfaces valuable patterns outside the first focused feature
set:

| Pattern | Deep Agents signal | Hermes signal | Recommendation |
| --- | --- | --- | --- |
| Child least privilege | Per-subagent tools and filesystem permissions | Blocked child tools and leaf defaults | Require explicit child tools and restrict recursive delegation when subagents are added |
| Human approval | `HumanInTheLoopMiddleware` for selected tools | Approval hooks and safe child auto-deny behavior | Keep approval policy separate from implemented information elicitation |
| Concurrency control | Concurrent independent `task` calls encouraged | Explicit maximum child count | Define a concurrency policy before supporting parent-driven parallel child work |
| Cancellation and timeout | Background cancel tool for remote tasks | Child timeout, heartbeat, and interruption | Require these contracts for future background work |
| Result isolation | Parent gets child final message/result | Parent gets concise summary | Use native ADK task isolation; do not leak child working history into parent reasoning |
| Large tool context | Summarization and argument trimming | Compression and cache resetting | Defer additional trimming until native ADK compaction is measured |
| Memory | Optional middleware | Memory manager around session lifecycle | Keep memory outside Phase 1 and design separately from the task ledger |

### ADK-Deep-Agent Recommendation

Treat these as design constraints for later capabilities, not reasons to
expand Phase 1. The first package surface should remain small and native to
ADK; subagent and background-job releases should adopt guardrails at the same
time as the execution feature rather than adding unsafe delegation first.

## 13. Conceptual Package Boundary

### Built Into the First Focused Surface

| Capability | Conceptual contract |
| --- | --- |
| App factory | Create and return a normal ADK `App` with an internal root `LlmAgent` |
| Planning | The built-in task ledger represents the persistent external plan |
| Task ledger | A built-in session-backed `todo` tool with active-context reinjection |
| Thinking | Optional explicit native ADK thinking configuration |
| Skills | Optional single developer-created ADK `SkillToolset` |
| Compaction | Optional native ADK event compaction with structured summaries |
| Extensions | Caller-supplied application-wide ADK plugins |
| Focused subagents | Native ADK prebuilt and on-demand `single_turn`/`task` children |
| Nested progress projection | Stable projection over raw ADK subagent events |
| Structured elicitation | Native ADK `request_input` with resumable UI request/response helpers |
| Model selection | Explicit model registry and validated spawned-agent model choice |

### Designed Here, Implemented Later

| Capability | Preferred pattern |
| --- | --- |
| Background subagents | Deep Agents-style job tools over an ADK-aligned durable executor |
| Advanced guardrails | Timeouts, cancellation, budgets, approvals, and explicit child policies |

### Explicit Non-Goals

`adk-deep-agent` should not:

1. Replace ADK `Runner`.
2. Port LangGraph middleware or require LangGraph.
3. Port the Hermes custom conversation loop.
4. Pretend ordinary `run_async(...)` is durable background delegation.
5. Treat a compaction summary as authoritative todo state.
6. Expose private ADK internal fields as stable public package contracts.

## 14. Selected Decisions

| Design concern | Selected direction |
| --- | --- |
| Runtime owner | Google ADK |
| Builder return type | Standard ADK `App` |
| Planning | Built-in todo ledger is the explicit task plan; native thinking remains separate |
| Todo API | Built-in Hermes-style single `todo` tool |
| Todo persistence | ADK session state |
| Todo request context | Root-agent callback |
| Todo competing writes | Reject before parallel tool dispatch |
| Skills input | One optional developer-created ADK `SkillToolset` |
| Thinking input | Explicit native config; no unqualified boolean enablement |
| Compaction | Native token-threshold-first ADK event compaction |
| Plugins | Caller-owned application-wide ADK plugins |
| Focused delegation | Native ADK `single_turn`/`task` children |
| True background work | Separate future durable task contract |
| User elicitation | Native ADK `request_input`; no package-owned blocking loop |
| Elicitation resume | Matching user-role `FunctionResponse` and retained invocation ID |
| Spawn model inventory | Explicit developer-provided registry; no per-call provider discovery |
| Spawn model validation | Tool execution validates against the same catalog shown to the root model |

## Source Index

### Deep Agents

| Area | Local source |
| --- | --- |
| Builder and middleware stack | [`deepagents/libs/deepagents/deepagents/graph.py`](deepagents/libs/deepagents/deepagents/graph.py) |
| Planning guidance | [`deepagents/libs/deepagents/deepagents/profiles/harness/_openai_codex.py`](deepagents/libs/deepagents/deepagents/profiles/harness/_openai_codex.py) |
| Focused task subagents | [`deepagents/libs/deepagents/deepagents/middleware/subagents.py`](deepagents/libs/deepagents/deepagents/middleware/subagents.py) |
| Remote background subagents | [`deepagents/libs/deepagents/deepagents/middleware/async_subagents.py`](deepagents/libs/deepagents/deepagents/middleware/async_subagents.py) |
| Child stream projection | [`deepagents/libs/deepagents/deepagents/_subagent_transformer.py`](deepagents/libs/deepagents/deepagents/_subagent_transformer.py) |
| Summarization | [`deepagents/libs/deepagents/deepagents/middleware/summarization.py`](deepagents/libs/deepagents/deepagents/middleware/summarization.py) |
| Skills | [`deepagents/libs/deepagents/deepagents/middleware/skills.py`](deepagents/libs/deepagents/deepagents/middleware/skills.py) |
| Parallel todo-write behavior | [`deepagents/libs/deepagents/tests/unit_tests/test_todo_middleware.py`](deepagents/libs/deepagents/tests/unit_tests/test_todo_middleware.py) |

### Hermes

| Area | Local source |
| --- | --- |
| Agent runtime | [`hermes-agent/run_agent.py`](hermes-agent/run_agent.py) |
| Todo tool | [`hermes-agent/tools/todo_tool.py`](hermes-agent/tools/todo_tool.py) |
| Delegated children | [`hermes-agent/tools/delegate_tool.py`](hermes-agent/tools/delegate_tool.py) |
| Conversation compression | [`hermes-agent/agent/conversation_compression.py`](hermes-agent/agent/conversation_compression.py) |
| Hook bridge | [`hermes-agent/agent/shell_hooks.py`](hermes-agent/agent/shell_hooks.py) |
| Skill index | [`hermes-agent/agent/prompt_builder.py`](hermes-agent/agent/prompt_builder.py) |

### Google ADK

| Area | Local source |
| --- | --- |
| Application container and compaction config export | [`adk-python/src/google/adk/apps/app.py`](adk-python/src/google/adk/apps/app.py) |
| Compaction execution | [`adk-python/src/google/adk/apps/compaction.py`](adk-python/src/google/adk/apps/compaction.py) |
| `LlmAgent`, tools, modes, planner | [`adk-python/src/google/adk/agents/llm_agent.py`](adk-python/src/google/adk/agents/llm_agent.py) |
| Task completion behavior | [`adk-python/src/google/adk/agents/llm/task/_finish_task_tool.py`](adk-python/src/google/adk/agents/llm/task/_finish_task_tool.py) |
| Task isolation/content handling | [`adk-python/src/google/adk/flows/llm_flows/contents.py`](adk-python/src/google/adk/flows/llm_flows/contents.py) |
| Concurrent function execution | [`adk-python/src/google/adk/flows/llm_flows/functions.py`](adk-python/src/google/adk/flows/llm_flows/functions.py) |
| Agent transfer behavior | [`adk-python/src/google/adk/flows/llm_flows/agent_transfer.py`](adk-python/src/google/adk/flows/llm_flows/agent_transfer.py) |
| Plugins | [`adk-python/src/google/adk/plugins/base_plugin.py`](adk-python/src/google/adk/plugins/base_plugin.py) |
| Native skill toolset | [`adk-python/src/google/adk/tools/skill_toolset.py`](adk-python/src/google/adk/tools/skill_toolset.py) |
| Native thinking planner | [`adk-python/src/google/adk/planners/built_in_planner.py`](adk-python/src/google/adk/planners/built_in_planner.py) |
| Optional plan/reason/act planner | [`adk-python/src/google/adk/planners/plan_re_act_planner.py`](adk-python/src/google/adk/planners/plan_re_act_planner.py) |

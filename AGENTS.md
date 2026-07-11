# Project Context

This repository is `adk-deep-agent`: a Python package that builds deep-agent
ergonomics on top of native Google ADK primitives.

The goal is to keep the package close to ADK concepts such as `App`,
`LlmAgent`, `ToolContext`, `Runner`, `SkillToolset`, tools, callbacks, events,
and subagents while adding a higher-level factory for deep-agent workflows.

Design reference repositories are cloned locally under `references/`:

- `references/hermes-agent` from `https://github.com/NousResearch/hermes-agent`
- `references/pi` from `https://github.com/earendil-works/pi`
- `references/deepagents` from `https://github.com/langchain-ai/deepagents`

Use these repositories as design references when shaping features. Compare
their approaches for planning, task ledgers, context management, compaction,
skills, subagents, tool execution, event streams, persistence, and ergonomics,
then adapt the best ideas into ADK-native APIs instead of copying large chunks
of implementation.

Keep `references/` local only. It is intentionally ignored by git so this
package does not vendor the reference projects.

## Agreed Design Direction

Model availability must be explicit. ADK gives an agent its configured
`model_client`, but it does not automatically expose every model available
from a provider to the LLM. For the initial design, accept a developer-passed
model list and keep one backend model registry as the source of truth. Inject
a concise static catalog of model IDs, descriptions, and capabilities into the
root instruction, and validate every model selected for a subagent against the
same registry. Keep provider clients, credentials, and secrets out of model
context. If model availability later becomes session- or tenant-dependent,
inject a precomputed catalog with a composable `before_model_callback`; do not
perform provider discovery on every model request.

Use ADK's native `request_input` tool for structured user elicitation. The LLM
calls `adk_request_input` with a message and JSON response schema, ADK emits a
long-running-tool interruption, and the client renders the corresponding UI.
While the invocation is waiting, no additional model or reflection call is
made. Resume with a user-role message containing a `FunctionResponse` whose
name and ID match the interrupted function call; do not resume with unrelated
plain user text. For multi-step or complex HITL flows, prefer a resumable ADK
`App` and retain the interrupted invocation ID.

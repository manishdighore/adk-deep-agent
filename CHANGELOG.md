# Changelog

## 0.2.0 - 2026-10-17

- Renamed the package to `adk-agent-harness` (import name `adk_agent_harness`).
  Package-owned session state keys now use the `adk_agent_harness:` prefix.
- Added a documentation site with guides for every feature and an API
  reference generated from docstrings, built with Zensical and published to
  GitHub Pages.
- Added opt-in native ADK `request_input` elicitation with resumability.
- Added stable elicitation event projection and response construction helpers.
- Added explicit model catalogs and validated model selection for spawned agents.
- Added optional sandbox workspaces (`local`, `daytona`, `e2b`, `cloud_run`) with
  build-time credential preflight and ADK `EnvironmentToolset` wiring.
- Added `use_sandbox` on prebuilt subagents and an `environment` entry in the
  spawned-subagent tool registry so children can share the root workspace.
- Added optional ADK context caching through `context_cache`.
- Spawned subagents now always run in ADK `single_turn` mode, mirroring ADK's
  single-turn agent tool: `goal` and `context` become the child request, and
  the child runs on a sub-branch keyed by the spawn function-call ID.
- Removed the spawn `mode` argument, the `waiting_for_user` spawn result, and
  the unused `SpawnConfig.default_mode`, `stream_mode`, and `max_depth` fields.
- Spawned subagents are never offered `adk_request_input`.
- Added `ToolCallRepairPlugin`, installed on every App, which answers tool calls
  left without a result (cancelled runs, crashes, or plain text sent while an
  elicitation is pending) with a synthetic interrupted result before each model
  request, without modifying stored history.
- Removed the `SubagentEvent`, `iter_subagent_events`, and
  `project_subagent_event` projection helpers. ADK already streams subagent
  activity as raw runner events tagged with the child's author and branch.
- Added `background=true` on `spawn_subagent`: the child runs in an isolated ADK
  runner session, the root agent continues, finished results are injected into
  the root's next model request, and raw child events can be streamed with
  `stream_background_task_events(task_id)`.
- Moved development tools from the published `dev` extra to a `dev`
  dependency group. Published extras are now only `daytona`, `e2b`, and
  `sandbox`; model clients and ADK session services are supplied by the app.
- Raised the minimum ADK version to 2.7.1 and aligned `google-genai` with ADK 2.7.x.

## 0.1.0 - 2026-05-30

Initial publishable package release.

- Added `create_deep_agent(...)` factory returning a standard Google ADK `App`.
- Added built-in session-backed `todo` task ledger.
- Added active ledger injection through ADK model callbacks.
- Added optional ADK `BuiltInPlanner` thinking configuration.
- Added optional ADK event compaction configuration.
- Added pass-through support for caller tools, one `SkillToolset`, and ADK plugins.
- Added prebuilt subagents through native ADK `sub_agents`.
- Added on-demand `spawn_subagent` tool backed by `ToolContext.run_node(...)`.
- Added raw ADK subagent event projection helpers.

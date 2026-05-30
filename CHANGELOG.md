# Changelog

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

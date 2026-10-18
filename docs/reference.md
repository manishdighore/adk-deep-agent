# API reference

Everything below is importable from `adk_agent_harness`.

## Factory

::: adk_agent_harness.create_deep_agent

## Configuration

::: adk_agent_harness.SubAgentSpec

::: adk_agent_harness.SpawnConfig

::: adk_agent_harness.ModelSpec

::: adk_agent_harness.ThinkingConfig

::: adk_agent_harness.CompactionConfig

::: adk_agent_harness.SandboxConfig

## Background subagents

::: adk_agent_harness.BackgroundTask

::: adk_agent_harness.get_background_task

::: adk_agent_harness.list_background_tasks

::: adk_agent_harness.stream_background_task_events

::: adk_agent_harness.wait_for_background_task

::: adk_agent_harness.cancel_background_task

## Asking the user

::: adk_agent_harness.ElicitationRequest

::: adk_agent_harness.project_elicitation_event

::: adk_agent_harness.create_elicitation_response

## Interrupted tool calls

::: adk_agent_harness.ToolCallRepairPlugin

::: adk_agent_harness.repair_dangling_tool_calls

## Sandbox helpers

::: adk_agent_harness.SandboxConfigurationError

::: adk_agent_harness.missing_sandbox_requirements

::: adk_agent_harness.describe_sandbox_requirements

::: adk_agent_harness.sandbox_requirements_report

::: adk_agent_harness.SandboxRequirements

## Task ledger

::: adk_agent_harness.TaskLedgerItem

::: adk_agent_harness.TaskLedgerResult

::: adk_agent_harness.TaskLedgerSummary

## Constants

| Name | Value | Meaning |
| --- | --- | --- |
| `LEDGER_STATE_KEY` | `"adk_agent_harness:todos"` | Session state key holding the task ledger |
| `REQUEST_INPUT_TOOL_NAME` | `"adk_request_input"` | ADK's elicitation tool name |
| `SANDBOX_TOOLSET_NAME` | `"environment"` | Tool name spawned subagents use to get the sandbox |
| `SANDBOX_REQUIREMENTS` | dict | Install and environment requirements per sandbox backend |

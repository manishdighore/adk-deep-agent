# Sandbox workspaces

Set `sandbox=` to give the agent a place to run commands and work with files.
The sandboxes themselves are **ADK features**: ADK's `EnvironmentToolset` and
its `LocalEnvironment`, `DaytonaEnvironment`, `E2BEnvironment`, and
`CloudRunSandboxCodeExecutor`. The package adds a one-word way to choose a
backend, checks credentials and packages when the agent is built, and shares
the workspace with subagents.

```python
app = create_deep_agent(
    name="data_analyst",
    model_client="gemini-3-flash-preview",
    instruction="Analyze the uploaded data inside the workspace.",
    sandbox="e2b",
)
```

`sandbox` accepts a backend name, a `SandboxConfig`, or an ADK
`BaseEnvironment` you built yourself.

## Backends

| Backend | Install | Required env vars | Optional env vars | Gives the agent |
| --- | --- | --- | --- | --- |
| `local` | included | none | none | Shell and file tools |
| `daytona` | `adk-agent-harness[daytona]` | `DAYTONA_API_KEY` | `DAYTONA_API_URL`, `DAYTONA_TARGET` | Shell and file tools |
| `e2b` | `adk-agent-harness[e2b]` | `E2B_API_KEY` | `E2B_DOMAIN` | Shell and file tools |
| `cloud_run` | included | none | `K_SERVICE` | Python code execution only |

- **`local`** runs commands as plain subprocesses of your process, **with no
  isolation**. Use a remote backend for untrusted work.
- **`daytona` / `e2b`** read their key from the environment. Setting
  `SandboxConfig(api_key=...)` instead also satisfies the check.
- **`cloud_run`** only works inside a Cloud Run container deployed with
  `gcloud beta run deploy --sandbox-launcher`, because it calls the guest binary
  at `/usr/local/gcp/bin/sandbox`.

Keys stay in your process environment or config. They never reach the model.

## How the agent uses it

**`local`, `daytona`, and `e2b`** add four ordinary tools:

| Tool | Arguments | Returns |
| --- | --- | --- |
| `Execute` | `command`: a shell command | `stdout`, `stderr`, exit code, timeout flag |
| `ReadFile` | `path`, optional `start_line`, `end_line` | File contents with line numbers |
| `WriteFile` | `path`, `content` | Creates or overwrites the file |
| `EditFile` | `path`, `old_string`, `new_string` | Replaces one exact match |

Code runs through the shell, typically `WriteFile` then
`Execute(command="python script.py")`. These are normal tool calls, so they
appear in the event stream like any other.

**`cloud_run`** has no tools. The model writes Python in a ```` ```tool_code ````
block in its reply; ADK's code-execution step extracts it, runs it in the
sandbox, and adds the output back as ```` ```tool_output ````. Runs share no
state.

## Lifetime: one sandbox per App

ADK ties a sandbox to an environment object, not to a session:

- The sandbox is **created on first use**: a temporary `adk_workspace_*`
  folder for `local` (unless you set `working_dir`), or a new remote sandbox
  for Daytona and E2B.
- It's **removed when the runner closes** its toolsets: the temporary folder is
  deleted, the Daytona sandbox is deleted, the E2B sandbox is killed.
- `create_deep_agent` builds **one environment per App**, so every session and
  user of that App shares the same sandbox.

!!! tip "Per-user sandboxes"
    For a multi-user app, give each user their own environment and App, and
    close the runner when the user is done:

    ```python
    from google.adk.integrations.e2b import E2BEnvironment

    app = create_deep_agent(..., sandbox=E2BEnvironment(timeout=600))
    runner = Runner(app=app, session_service=session_service)
    ...
    await runner.close()  # kills that user's sandbox
    ```

## Configuration

```python
from adk_agent_harness import SandboxConfig

SandboxConfig(
    kind="daytona",
    image="python:3.12",          # daytona/e2b: template, snapshot, or image
    timeout=600,                  # daytona/e2b: sandbox time-to-live, seconds
    env_vars={"MODE": "report"},  # set inside the sandbox, not in your process
    max_output_chars=20_000,      # truncate tool output shown to the model
)
```

See [`SandboxConfig`](../reference.md#adk_agent_harness.SandboxConfig) for every
field, including `working_dir` for `local` and `allow_egress` for `cloud_run`.

## Build-time checks

Missing credentials or packages raise `SandboxConfigurationError` when the agent
is built, instead of failing on the first tool call. You can also check ahead
of time:

```python
from adk_agent_harness import SandboxConfig, missing_sandbox_requirements, sandbox_requirements_report

print(sandbox_requirements_report())                     # setup table for every backend
missing_sandbox_requirements(SandboxConfig(kind="e2b"))  # [] when ready
```

Set `validate_environment=False` to skip the check, for example when building
the agent in CI for a different environment.

## Sharing the workspace with subagents

The root and its children see the same files:

- Prebuilt subagents opt in with `SubAgentSpec(use_sandbox=True)`.
- Spawned subagents can be given the tool named `environment`
  (`SANDBOX_TOOLSET_NAME`).

```python
from adk_agent_harness import SANDBOX_TOOLSET_NAME, SpawnConfig, SubAgentSpec

app = create_deep_agent(
    name="lead",
    model_client="gemini-3-flash-preview",
    instruction="Delegate data preparation, then write the report.",
    sandbox="local",
    subagents=[SubAgentSpec(name="cleaner", goal="Clean the raw data files.", use_sandbox=True)],
    spawn=SpawnConfig(enabled=True, allowed_tools=[SANDBOX_TOOLSET_NAME]),
)
```

A subagent that sets `use_sandbox=True` when no sandbox is configured raises a
`ValueError` at build time.

"""Sandbox environment configuration for adk-agent-harness.

The package maps a small declarative `SandboxConfig` onto native ADK
primitives:

- `local`, `daytona`, and `e2b` build an ADK `BaseEnvironment` and attach it
  through ADK's `EnvironmentToolset` (`Execute`, `ReadFile`, `EditFile`,
  `WriteFile`).
- `cloud_run` attaches ADK's `CloudRunSandboxCodeExecutor` as the agent code
  executor. Cloud Run sandboxes execute code only; they provide no file tools.

Every backend is preflighted before the agent is built so misconfigured
credentials fail at construction time instead of on the first tool call.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from google.adk.code_executors.base_code_executor import BaseCodeExecutor
from google.adk.environment import BaseEnvironment
from google.adk.tools.environment import EnvironmentToolset
from pydantic import BaseModel, ConfigDict, Field

SandboxKind = Literal["local", "daytona", "e2b", "cloud_run"]

SANDBOX_TOOLSET_NAME = "environment"
"""Registry name under which the sandbox toolset is offered to spawned agents."""

CLOUD_RUN_SANDBOX_BIN = "/usr/local/gcp/bin/sandbox"
"""Default guest sandbox binary inside a sandbox-enabled Cloud Run container."""


class SandboxRequirements(BaseModel):
    """Environment variables and packages one sandbox backend needs."""

    kind: SandboxKind
    required_env_vars: tuple[str, ...] = ()
    optional_env_vars: tuple[str, ...] = ()
    python_package: str | None = None
    install_extra: str | None = None
    notes: str = ""


SANDBOX_REQUIREMENTS: dict[SandboxKind, SandboxRequirements] = {
    "local": SandboxRequirements(
        kind="local",
        notes=(
            "Runs shell commands as local subprocesses with no isolation. "
            "Requires no credentials. Use `working_dir` to pin the workspace; "
            "otherwise ADK creates and removes a temporary directory."
        ),
    ),
    "daytona": SandboxRequirements(
        kind="daytona",
        required_env_vars=("DAYTONA_API_KEY",),
        optional_env_vars=("DAYTONA_API_URL", "DAYTONA_TARGET"),
        python_package="daytona",
        install_extra="daytona",
        notes=(
            "Remote Daytona workspace. `DAYTONA_API_KEY` is required unless "
            "`api_key` is set on the config. `DAYTONA_API_URL` defaults to the "
            "Daytona Cloud API and `DAYTONA_TARGET` selects the region."
        ),
    ),
    "e2b": SandboxRequirements(
        kind="e2b",
        required_env_vars=("E2B_API_KEY",),
        optional_env_vars=("E2B_DOMAIN",),
        python_package="e2b",
        install_extra="e2b",
        notes=(
            "Remote E2B sandbox. `E2B_API_KEY` is required unless `api_key` is "
            "set on the config. `E2B_DOMAIN` targets a self-hosted deployment."
        ),
    ),
    "cloud_run": SandboxRequirements(
        kind="cloud_run",
        optional_env_vars=("K_SERVICE",),
        notes=(
            "Code execution only, with no file tools. Runs exclusively inside a "
            "Cloud Run container deployed with the sandbox launcher enabled "
            "(`gcloud beta run deploy --sandbox-launcher`), because it shells "
            f"out to the guest binary at {CLOUD_RUN_SANDBOX_BIN}. Cloud Run "
            "sets `K_SERVICE` inside the container."
        ),
    ),
}


class SandboxConfigurationError(RuntimeError):
    """Raised when a sandbox backend is selected but not usable."""


class SandboxConfig(BaseModel):
    """Declarative sandbox configuration for `create_deep_agent`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: SandboxKind = "local"

    working_dir: str | Path | None = None
    """`local` only. Workspace directory; a temporary one is used when unset."""

    image: str | None = None
    """`daytona` and `e2b` only. Template, snapshot, or image name."""

    timeout: int = Field(default=300, gt=0)
    """`daytona` and `e2b` only. Sandbox time-to-live in seconds."""

    api_key: str | None = None
    """`daytona` and `e2b` only. Overrides the backend API-key env var."""

    api_url: str | None = None
    """`daytona` only. Overrides `DAYTONA_API_URL`."""

    env_vars: Mapping[str, str] = Field(default_factory=dict)
    """Environment variables set inside the sandbox, not in this process."""

    max_output_chars: int | None = None
    """Truncation limit applied to sandbox tool output before the model sees it."""

    sandbox_bin: str | None = None
    """`cloud_run` only. Overrides the guest sandbox binary path."""

    allow_egress: bool = False
    """`cloud_run` only. Whether the sandbox may reach the network."""

    validate_environment: bool = True
    """Preflight credentials and packages while building the agent."""


class SandboxAttachment(BaseModel):
    """Resolved sandbox wiring returned to the factory."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: SandboxKind | None = None
    environment: BaseEnvironment | None = None
    toolset: EnvironmentToolset | None = None
    code_executor: BaseCodeExecutor | None = None


def describe_sandbox_requirements(kind: SandboxKind) -> str:
    """Return human-readable setup requirements for one sandbox backend."""

    requirements = SANDBOX_REQUIREMENTS[kind]
    lines = [f"sandbox `{kind}`:"]
    if requirements.install_extra:
        lines.append(
            f"- install: pip install \"google-adk[{requirements.install_extra}]\""
        )
    if requirements.required_env_vars:
        lines.append("- required env vars: " + ", ".join(requirements.required_env_vars))
    if requirements.optional_env_vars:
        lines.append("- optional env vars: " + ", ".join(requirements.optional_env_vars))
    if requirements.notes:
        lines.append(f"- notes: {requirements.notes}")
    return "\n".join(lines)


def missing_sandbox_requirements(config: SandboxConfig) -> list[str]:
    """Return unmet requirements for a sandbox config, in report order."""

    requirements = SANDBOX_REQUIREMENTS[config.kind]
    missing: list[str] = []

    if requirements.python_package and not importlib.util.find_spec(
        requirements.python_package
    ):
        missing.append(
            f"missing package `{requirements.python_package}`; install with "
            f"`pip install \"google-adk[{requirements.install_extra}]\"`"
        )

    if config.api_key is None:
        for env_var in requirements.required_env_vars:
            if not os.environ.get(env_var):
                missing.append(f"missing environment variable `{env_var}`")

    if config.kind == "cloud_run":
        sandbox_bin = config.sandbox_bin or CLOUD_RUN_SANDBOX_BIN
        if not Path(sandbox_bin).exists():
            missing.append(
                f"missing Cloud Run sandbox binary `{sandbox_bin}`; this backend "
                "runs only inside a Cloud Run container deployed with "
                "`gcloud beta run deploy --sandbox-launcher`"
            )

    return missing


def _check_sandbox_requirements(config: SandboxConfig) -> None:
    if not config.validate_environment:
        return
    missing = missing_sandbox_requirements(config)
    if not missing:
        return
    details = "\n".join(f"- {item}" for item in missing)
    raise SandboxConfigurationError(
        f"sandbox `{config.kind}` is not configured:\n{details}\n\n"
        f"{describe_sandbox_requirements(config.kind)}"
    )


def build_environment(config: SandboxConfig) -> BaseEnvironment:
    """Build the ADK environment for a filesystem-capable sandbox backend."""

    env_vars = dict(config.env_vars) or None

    if config.kind == "local":
        return _build_local_environment(config, env_vars)
    if config.kind == "daytona":
        return _build_daytona_environment(config, env_vars)
    if config.kind == "e2b":
        return _build_e2b_environment(config, env_vars)
    raise SandboxConfigurationError(
        f"sandbox `{config.kind}` provides no filesystem environment"
    )


def _build_local_environment(
    config: SandboxConfig,
    env_vars: dict[str, str] | None,
) -> BaseEnvironment:
    from google.adk.environment import LocalEnvironment

    return LocalEnvironment(
        working_dir=Path(config.working_dir) if config.working_dir else None,
        env_vars=env_vars,
    )


def _build_daytona_environment(
    config: SandboxConfig,
    env_vars: dict[str, str] | None,
) -> BaseEnvironment:
    try:
        from google.adk.integrations.daytona import DaytonaEnvironment
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SandboxConfigurationError(
            describe_sandbox_requirements("daytona")
        ) from exc

    return DaytonaEnvironment(
        image=config.image,
        timeout=config.timeout,
        api_key=config.api_key,
        api_url=config.api_url,
        env_vars=env_vars,
    )


def _build_e2b_environment(
    config: SandboxConfig,
    env_vars: dict[str, str] | None,
) -> BaseEnvironment:
    try:
        from google.adk.integrations.e2b import E2BEnvironment
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SandboxConfigurationError(
            describe_sandbox_requirements("e2b")
        ) from exc

    kwargs: dict[str, object] = {
        "timeout": config.timeout,
        "api_key": config.api_key,
        "env_vars": env_vars,
    }
    if config.image is not None:
        kwargs["image"] = config.image
    return E2BEnvironment(**kwargs)


def _build_cloud_run_code_executor(config: SandboxConfig) -> BaseCodeExecutor:
    try:
        from google.adk.integrations.cloud_run import CloudRunSandboxCodeExecutor
    except ImportError as exc:  # pragma: no cover - shipped with ADK
        raise SandboxConfigurationError(
            describe_sandbox_requirements("cloud_run")
        ) from exc

    kwargs: dict[str, object] = {"allow_egress": config.allow_egress}
    if config.sandbox_bin is not None:
        kwargs["sandbox_bin"] = config.sandbox_bin
    return CloudRunSandboxCodeExecutor(**kwargs)


def normalize_sandbox(
    sandbox: SandboxKind | SandboxConfig | BaseEnvironment | None,
) -> SandboxConfig | BaseEnvironment | None:
    """Coerce the factory `sandbox` argument into a config or ADK environment."""

    if sandbox is None:
        return None
    if isinstance(sandbox, BaseEnvironment):
        return sandbox
    if isinstance(sandbox, SandboxConfig):
        return sandbox
    if isinstance(sandbox, str):
        if sandbox not in SANDBOX_REQUIREMENTS:
            supported = ", ".join(sorted(SANDBOX_REQUIREMENTS))
            raise ValueError(f"unknown sandbox `{sandbox}`; expected one of: {supported}")
        return SandboxConfig(kind=sandbox)
    raise TypeError(
        "sandbox must be a sandbox name, SandboxConfig, ADK BaseEnvironment, or None"
    )


def build_sandbox(
    sandbox: SandboxKind | SandboxConfig | BaseEnvironment | None,
) -> SandboxAttachment:
    """Resolve the factory `sandbox` argument into ADK tooling."""

    normalized = normalize_sandbox(sandbox)
    if normalized is None:
        return SandboxAttachment()

    if isinstance(normalized, BaseEnvironment):
        return SandboxAttachment(
            environment=normalized,
            toolset=EnvironmentToolset(environment=normalized),
        )

    _check_sandbox_requirements(normalized)

    if normalized.kind == "cloud_run":
        return SandboxAttachment(
            kind=normalized.kind,
            code_executor=_build_cloud_run_code_executor(normalized),
        )

    environment = build_environment(normalized)
    return SandboxAttachment(
        kind=normalized.kind,
        environment=environment,
        toolset=EnvironmentToolset(
            environment=environment,
            max_output_chars=normalized.max_output_chars,
        ),
    )


def sandbox_requirements_report(
    kinds: Sequence[SandboxKind] = ("local", "daytona", "e2b", "cloud_run"),
) -> str:
    """Return setup requirements for the given sandbox backends."""

    return "\n\n".join(describe_sandbox_requirements(kind) for kind in kinds)

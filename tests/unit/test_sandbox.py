import asyncio
from pathlib import Path

import pytest
from adk_agent_harness import ModelSpec
from adk_agent_harness import SandboxConfig
from adk_agent_harness import SandboxConfigurationError
from adk_agent_harness import SpawnConfig
from adk_agent_harness import SubAgentSpec
from adk_agent_harness import create_deep_agent
from adk_agent_harness import describe_sandbox_requirements
from adk_agent_harness import missing_sandbox_requirements
from adk_agent_harness.sandbox import CLOUD_RUN_SANDBOX_BIN
from adk_agent_harness.sandbox import SANDBOX_TOOLSET_NAME
from adk_agent_harness.sandbox import build_sandbox
from adk_agent_harness.sandbox import normalize_sandbox
from google.adk.environment import LocalEnvironment
from google.adk.tools.environment import EnvironmentToolset


def _environment_toolsets(agent) -> list[EnvironmentToolset]:
    return [tool for tool in agent.tools if isinstance(tool, EnvironmentToolset)]


def test_local_sandbox_attaches_environment_toolset(tmp_path: Path) -> None:
    app = create_deep_agent(
        name="sandboxed_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="local", working_dir=tmp_path),
    )

    toolsets = _environment_toolsets(app.root_agent)
    assert len(toolsets) == 1
    assert app.root_agent.code_executor is None


def test_sandbox_accepts_backend_name() -> None:
    app = create_deep_agent(
        name="sandboxed_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox="local",
    )

    assert len(_environment_toolsets(app.root_agent)) == 1


def test_sandbox_accepts_prebuilt_environment(tmp_path: Path) -> None:
    environment = LocalEnvironment(working_dir=tmp_path)

    attachment = build_sandbox(environment)

    assert attachment.environment is environment
    assert isinstance(attachment.toolset, EnvironmentToolset)


def test_no_sandbox_by_default() -> None:
    app = create_deep_agent(
        name="plain_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
    )

    assert _environment_toolsets(app.root_agent) == []
    assert app.root_agent.code_executor is None


def test_local_sandbox_tools_execute_in_workspace(tmp_path: Path) -> None:
    attachment = build_sandbox(SandboxConfig(kind="local", working_dir=tmp_path))

    async def run() -> dict:
        tools = await attachment.toolset.get_tools()
        assert [tool.name for tool in tools] == [
            "Execute",
            "ReadFile",
            "EditFile",
            "WriteFile",
        ]
        write = next(tool for tool in tools if tool.name == "WriteFile")
        result = await write.run_async(
            args={"path": "note.txt", "content": "sandbox"},
            tool_context=None,
        )
        await attachment.toolset.close()
        return result

    asyncio.run(run())
    assert (tmp_path / "note.txt").read_text() == "sandbox"


def test_unknown_sandbox_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown sandbox"):
        normalize_sandbox("docker")


def test_unsupported_sandbox_type_is_rejected() -> None:
    with pytest.raises(TypeError):
        normalize_sandbox(object())


def test_missing_credentials_fail_at_build_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    with pytest.raises(SandboxConfigurationError) as excinfo:
        create_deep_agent(
            name="sandboxed_agent",
            model_client="gemini-3-flash-preview",
            instruction="Help.",
            sandbox="e2b",
        )

    assert "E2B_API_KEY" in str(excinfo.value)


def test_explicit_api_key_satisfies_env_var_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)

    missing = missing_sandbox_requirements(
        SandboxConfig(kind="daytona", api_key="explicit-key")
    )

    assert all("DAYTONA_API_KEY" not in item for item in missing)


def test_cloud_run_requires_guest_sandbox_binary() -> None:
    missing = missing_sandbox_requirements(SandboxConfig(kind="cloud_run"))

    if Path(CLOUD_RUN_SANDBOX_BIN).exists():
        assert missing == []
    else:
        assert any(CLOUD_RUN_SANDBOX_BIN in item for item in missing)


def test_cloud_run_sandbox_attaches_code_executor_without_file_tools() -> None:
    app = create_deep_agent(
        name="cloud_run_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="cloud_run", validate_environment=False),
    )

    assert _environment_toolsets(app.root_agent) == []
    assert app.root_agent.code_executor is not None


def test_validation_can_be_disabled() -> None:
    config = SandboxConfig(kind="cloud_run", validate_environment=False)

    # Requirements are still reported, but building no longer raises.
    assert missing_sandbox_requirements(config) != [] or Path(
        CLOUD_RUN_SANDBOX_BIN
    ).exists()
    assert build_sandbox(config).code_executor is not None


def test_requirements_description_lists_env_vars_and_extra() -> None:
    described = describe_sandbox_requirements("daytona")

    assert "DAYTONA_API_KEY" in described
    assert "DAYTONA_API_URL" in described
    assert 'pip install "google-adk[daytona]"' in described


def test_prebuilt_subagent_opts_into_sandbox(tmp_path: Path) -> None:
    app = create_deep_agent(
        name="root_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="local", working_dir=tmp_path),
        subagents=[
            SubAgentSpec(name="builder", goal="Build things.", use_sandbox=True),
            SubAgentSpec(name="reviewer", goal="Review things."),
        ],
    )

    builder, reviewer = app.root_agent.sub_agents
    assert len(_environment_toolsets(builder)) == 1
    assert _environment_toolsets(reviewer) == []


def test_prebuilt_subagents_share_the_root_workspace(tmp_path: Path) -> None:
    app = create_deep_agent(
        name="root_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="local", working_dir=tmp_path),
        subagents=[SubAgentSpec(name="builder", goal="Build.", use_sandbox=True)],
    )

    root_toolset = _environment_toolsets(app.root_agent)[0]
    child_toolset = _environment_toolsets(app.root_agent.sub_agents[0])[0]
    assert root_toolset is child_toolset


def test_sandbox_is_offered_to_spawned_subagents(tmp_path: Path) -> None:
    from adk_agent_harness.subagents import build_tool_registry

    attachment = build_sandbox(SandboxConfig(kind="local", working_dir=tmp_path))
    registry = build_tool_registry((), {}, sandbox_toolset=attachment.toolset)

    assert registry[SANDBOX_TOOLSET_NAME] is attachment.toolset

    app = create_deep_agent(
        name="root_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="local", working_dir=tmp_path),
        spawn=SpawnConfig(enabled=True, allowed_tools=[SANDBOX_TOOLSET_NAME]),
    )

    assert any(getattr(tool, "name", "") == "spawn_subagent" for tool in app.root_agent.tools)


def test_subagent_sandbox_request_without_sandbox_is_rejected() -> None:
    with pytest.raises(ValueError, match="request a sandbox but none is configured"):
        create_deep_agent(
            name="root_agent",
            model_client="gemini-3-flash-preview",
            instruction="Help.",
            subagents=[
                SubAgentSpec(name="builder", goal="Build.", use_sandbox=True),
            ],
        )


def test_cloud_run_sandbox_reaches_opted_in_subagents() -> None:
    app = create_deep_agent(
        name="root_agent",
        model_client="gemini-3-flash-preview",
        instruction="Help.",
        sandbox=SandboxConfig(kind="cloud_run", validate_environment=False),
        subagents=[
            SubAgentSpec(name="builder", goal="Build.", use_sandbox=True),
            SubAgentSpec(name="planner", goal="Plan."),
        ],
    )

    builder, planner = app.root_agent.sub_agents
    assert builder.code_executor is not None
    assert planner.code_executor is None


@pytest.mark.asyncio
async def test_spawned_child_writes_into_the_shared_workspace(tmp_path: Path) -> None:
    from test_subagents import FakeModel
    from test_subagents import _function_call
    from test_subagents import _run_app
    from adk_agent_harness.subagents import SPAWN_TOOL_NAME

    child_model = FakeModel(
        responses=[
            _function_call(
                "WriteFile",
                {"path": "spawned.txt", "content": "from the child"},
            ),
            "wrote the file",
        ]
    )
    root_model = FakeModel(
        responses=[
            _function_call(
                SPAWN_TOOL_NAME,
                {
                    "name": "temp_builder",
                    "goal": "Write a file.",
                    "tool_names": [SANDBOX_TOOLSET_NAME],
                    "model": "child",
                },
            ),
            "root done",
        ]
    )

    app = create_deep_agent(
        name="root",
        model_client=root_model,
        instruction="Help.",
        sandbox=SandboxConfig(kind="local", working_dir=tmp_path),
        available_models=[ModelSpec(id="child", model_client=child_model)],
        spawn=SpawnConfig(enabled=True, allowed_tools=[SANDBOX_TOOLSET_NAME]),
    )

    events = await _run_app(app)

    assert any(event.author == "temp_builder" for event in events)
    assert (tmp_path / "spawned.txt").read_text() == "from the child"

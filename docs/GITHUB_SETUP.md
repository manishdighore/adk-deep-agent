# GitHub Setup

Suggested repository description:

```text
Deep-agent ergonomics on top of native Google ADK primitives.
```

Suggested topics:

```text
adk
agent-development-kit
ai-agents
deep-agent
google-adk
llm
multi-agent
subagents
task-delegation
python
```

Suggested repository settings:

- Enable Issues.
- Enable Discussions if you want design/API conversations outside issues.
- Enable branch protection on `main`.
- Require the `CI` workflow before merging.
- Configure PyPI Trusted Publishing for the `Publish` workflow and `pypi` environment.

For PyPI Trusted Publishing, create a pending publisher on PyPI with:

- Owner: `manishdighore`
- Repository: `adk-agent-harness`
- Workflow: `publish.yml`
- Environment: `pypi`

# Model selection

ADK gives each agent one model. It doesn't tell the model which other models
exist. With `available_models`, you declare the models a
[spawned subagent](subagents.md#spawned-subagents) may run on, and the root
agent picks one per child.

```python
from google.adk.models.lite_llm import LiteLlm

from adk_agent_harness import ModelSpec, SpawnConfig, create_deep_agent

app = create_deep_agent(
    name="lead",
    model_client="gemini-3-flash-preview",
    instruction="Delegate hard reviews to a stronger model.",
    available_models=[
        ModelSpec(
            id="strong",
            model_client="gemini-3-pro-preview",
            description="Difficult reasoning and review work.",
            capabilities=["reasoning", "review"],
        ),
        ModelSpec(
            id="claude",
            model_client=LiteLlm(model="anthropic/claude-sonnet-4-5"),
            description="Long-form writing.",
        ),
    ],
    spawn=SpawnConfig(enabled=True),
)
```

## What the model sees

When spawning is enabled, a short catalog is added to the root instruction:

```text
Available models for `spawn_subagent`:
Select only a model ID from this catalog. Omit `model` to use the default.
- `gemini-3-flash-preview` - default; Default model used by the root agent.
- `strong` - Difficult reasoning and review work.; capabilities: reasoning, review
- `claude` - Long-form writing.
```

Only IDs, descriptions, and capability tags reach the model. Model clients,
endpoints, and credentials stay in the backend registry.

## Rules

- The root model is always in the catalog and is the default when the agent
  omits `model`.
- Every selected ID is checked against the same registry. An unknown ID returns
  an error to the agent instead of running.
- A plain string in `available_models` is both the ID and the model name.
  `ModelSpec.model_client` defaults to its `id`.
- IDs must be unique, and an entry can't reuse the root model's ID with a
  different client.
- Prebuilt subagents don't use the catalog. Set `SubAgentSpec.model_client`
  directly.

If the set of models depends on the tenant or session, build the App per
tenant with that tenant's list. The catalog is fixed when the App is built,
and the package never discovers models from a provider at request time.

# Thinking, compaction, caching

These map directly onto ADK features. The package gives each a short setting.

## Thinking

```python
from adk_agent_harness import ThinkingConfig

app = create_deep_agent(
    ...,
    thinking=ThinkingConfig(include_thoughts=True, thinking_budget=2048),
)
```

`thinking=True` uses the model's defaults. `ThinkingConfig` maps to ADK's
`BuiltInPlanner`:

- `include_thoughts=True` asks the model to return thought summaries. They
  arrive as event parts with `part.thought == True`, so a UI can show
  reasoning.
- `thinking_budget` caps thinking tokens.

Prebuilt subagents take the same values through `SubAgentSpec.thinking`.
Spawned subagents don't set thinking.

## Compaction

Long sessions eventually outgrow the context window. Compaction summarizes
older history once the prompt gets large:

```python
from adk_agent_harness import CompactionConfig

app = create_deep_agent(
    ...,
    compaction=CompactionConfig(token_threshold=100_000, event_retention_size=20),
)
```

This turns on ADK's event compaction with `LlmEventSummarizer`, using the root
model and a summary prompt written for long-running work. The summary captures:

1. the user's goal and constraints;
2. completed actions and results;
3. changed files, resources, or outputs;
4. outstanding issues;
5. the next intended action.

The [task ledger](task-ledger.md) lives in session state, outside the
conversation, so compaction never loses the plan.

| Field | Default | Meaning |
| --- | --- | --- |
| `token_threshold` | required | Prompt size, in tokens, that triggers compaction |
| `event_retention_size` | `20` | Recent events kept verbatim |
| `compaction_interval` | `999` | ADK's invocation-count trigger; the high default leaves token size in charge |
| `overlap_size` | `0` | Events shared between compaction windows |

ADK reads the prompt size from the model's reported usage, and falls back to an
estimate when a provider doesn't report it.

## Context caching

```python
from google.adk.agents.context_cache_config import ContextCacheConfig

app = create_deep_agent(..., context_cache=True)                     # ADK defaults
app = create_deep_agent(..., context_cache=ContextCacheConfig(ttl_seconds=900))
```

Caching pays off when a long session keeps re-sending a large, stable prefix:
instructions, skills, and tool declarations. The value is passed straight to
`App.context_cache_config`, and caching is off when you leave it out.

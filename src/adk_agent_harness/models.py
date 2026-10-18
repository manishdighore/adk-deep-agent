"""Model registry helpers for spawned agents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from google.adk.models import BaseLlm
from pydantic import BaseModel, ConfigDict, Field


class ModelSpec(BaseModel):
    """A model exposed to the root agent for spawned-agent selection."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    """ID the model selects in `spawn_subagent(model=...)`."""

    model_client: str | BaseLlm | None = None
    """Model name or ADK `BaseLlm`. Defaults to `id`. Never shown to the model."""

    description: str = ""
    """When to use this model, shown to the root agent."""

    capabilities: Sequence[str] = Field(default_factory=tuple)
    """Short capability tags shown to the root agent, such as `reasoning`."""


def model_client_id(model_client: str | BaseLlm) -> str:
    """Return a stable public identifier for an ADK model client."""

    if isinstance(model_client, str):
        model_id = model_client
    else:
        model_id = getattr(model_client, "model", "")
    model_id = str(model_id).strip()
    if not model_id:
        raise ValueError("model clients must expose a non-empty model identifier")
    return model_id


def build_model_registry(
    *,
    default_model_client: str | BaseLlm,
    available_models: Sequence[str | ModelSpec],
) -> tuple[str, dict[str, ModelSpec]]:
    """Build the validated model registry used by context and spawn tools."""

    default_id = model_client_id(default_model_client)
    registry = {
        default_id: ModelSpec(
            id=default_id,
            model_client=default_model_client,
            description="Default model used by the root agent.",
        )
    }
    configured_ids: set[str] = set()

    for raw_spec in available_models:
        spec = ModelSpec(id=raw_spec) if isinstance(raw_spec, str) else raw_spec
        model_id = spec.id.strip()
        if not model_id:
            raise ValueError("model IDs cannot be empty")
        if model_id in configured_ids:
            raise ValueError(f"duplicate model ID: {model_id}")
        if (
            model_id == default_id
            and spec.model_client is not None
            and spec.model_client != default_model_client
        ):
            raise ValueError(f"model ID conflicts with the root model: {model_id}")
        registry[model_id] = spec.model_copy(
            update={
                "id": model_id,
                "model_client": spec.model_client or model_id,
            }
        )
        configured_ids.add(model_id)

    return default_id, registry


def format_model_catalog(
    registry: Mapping[str, ModelSpec],
    *,
    default_model_id: str,
) -> str:
    """Format model metadata for root-agent instruction context."""

    lines = [
        "Available models for `spawn_subagent`:",
        "Select only a model ID from this catalog. Omit `model` to use the default.",
    ]
    for model_id, spec in registry.items():
        details: list[str] = []
        if model_id == default_model_id:
            details.append("default")
        if spec.description:
            details.append(spec.description.strip())
        if spec.capabilities:
            details.append("capabilities: " + ", ".join(spec.capabilities))
        suffix = f" - {'; '.join(details)}" if details else ""
        lines.append(f"- `{model_id}`{suffix}")
    return "\n".join(lines)

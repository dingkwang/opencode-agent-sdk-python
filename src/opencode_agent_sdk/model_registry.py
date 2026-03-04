"""Generic model registry for mapping user-friendly aliases to model configurations.

Provides a pluggable registry that SDK consumers can populate with their own
model aliases and provider mappings. No vendor-specific defaults are included.

Usage::

    from opencode_agent_sdk.model_registry import ModelConfig, ModelRegistry

    registry = ModelRegistry()
    registry.register("my-model", ModelConfig("actual-model-id", "my-provider"))

    config = registry.resolve("my-model")
    if config:
        options = AgentOptions(model=config.model_id, provider_id=config.provider_id)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration mapping an alias to its actual model and provider IDs."""

    model_id: str
    provider_id: str


class ModelRegistry:
    """Registry for model alias → (model_id, provider_id) mappings.

    Thread-safe for reads; callers should populate the registry at startup
    before concurrent access.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, alias: str, config: ModelConfig) -> None:
        """Register a model alias.

        Args:
            alias: User-friendly name (stored lowercase).
            config: Model configuration with model_id and provider_id.
        """
        self._models[alias.lower()] = config

    def register_many(self, models: dict[str, ModelConfig]) -> None:
        """Register multiple model aliases at once.

        Args:
            models: Mapping of alias → ModelConfig.
        """
        for alias, config in models.items():
            self._models[alias.lower()] = config

    def resolve(self, alias: str) -> ModelConfig | None:
        """Resolve a user-friendly alias to a ModelConfig.

        Args:
            alias: Model alias (case-insensitive lookup).

        Returns:
            ModelConfig if alias is known, None otherwise.
        """
        return self._models.get(alias.lower())

    def list_models(self) -> dict[str, ModelConfig]:
        """Return a copy of all registered models."""
        return dict(self._models)

    def format_help(self) -> str:
        """Return a formatted list of available models for user-facing help."""
        if not self._models:
            return "No models registered."
        lines = ["Available models:"]
        for alias, config in sorted(self._models.items()):
            lines.append(f"  {alias} -> {config.model_id} (provider: {config.provider_id})")
        return "\n".join(lines)

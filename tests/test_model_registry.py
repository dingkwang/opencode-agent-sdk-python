"""Tests for the generic ModelRegistry in the SDK."""

import pytest
from opencode_agent_sdk.model_registry import ModelConfig, ModelRegistry


class TestModelRegistry:
    def test_register_and_resolve(self):
        registry = ModelRegistry()
        registry.register("test-model", ModelConfig("actual-id", "test-provider"))
        config = registry.resolve("test-model")
        assert config is not None
        assert config.model_id == "actual-id"
        assert config.provider_id == "test-provider"

    def test_resolve_case_insensitive(self):
        registry = ModelRegistry()
        registry.register("My-Model", ModelConfig("id", "provider"))
        assert registry.resolve("my-model") is not None
        assert registry.resolve("MY-MODEL") is not None

    def test_resolve_unknown_returns_none(self):
        registry = ModelRegistry()
        assert registry.resolve("nonexistent") is None

    def test_register_many(self):
        registry = ModelRegistry()
        registry.register_many({
            "model-a": ModelConfig("a-id", "a-provider"),
            "model-b": ModelConfig("b-id", "b-provider"),
        })
        assert registry.resolve("model-a") is not None
        assert registry.resolve("model-b") is not None

    def test_list_models(self):
        registry = ModelRegistry()
        registry.register("x", ModelConfig("x-id", "x-provider"))
        models = registry.list_models()
        assert "x" in models
        assert models["x"].model_id == "x-id"

    def test_list_models_returns_copy(self):
        registry = ModelRegistry()
        registry.register("x", ModelConfig("x-id", "x-provider"))
        models = registry.list_models()
        models["y"] = ModelConfig("y-id", "y-provider")
        assert registry.resolve("y") is None

    def test_format_help_empty(self):
        registry = ModelRegistry()
        assert "No models registered" in registry.format_help()

    def test_format_help_with_models(self):
        registry = ModelRegistry()
        registry.register("my-model", ModelConfig("real-id", "my-provider"))
        help_text = registry.format_help()
        assert "my-model" in help_text
        assert "real-id" in help_text
        assert "my-provider" in help_text

    def test_model_config_frozen(self):
        config = ModelConfig("id", "provider")
        with pytest.raises(AttributeError):
            config.model_id = "changed"

"""Model type definitions."""

from enum import Enum


class ModelType(str, Enum):
    """Supported model types."""

    GPT5 = "gpt5"
    GPT5_MINI = "gpt5mini"
    OPUS = "opus"
    SONNET = "sonnet"

    @property
    def model_name(self) -> str:
        return {
            ModelType.GPT5: "openai/gpt-5.4",
            ModelType.GPT5_MINI: "openai/gpt-5.4-mini",
            ModelType.OPUS: "anthropic/claude-opus-4.6",
            ModelType.SONNET: "anthropic/claude-sonnet-4.6",
        }[self]

    @property
    def display_name(self) -> str:
        return {
            ModelType.GPT5: "GPT-5.4",
            ModelType.GPT5_MINI: "GPT-5.4-mini",
            ModelType.OPUS: "Claude Opus 4.6",
            ModelType.SONNET: "Claude Sonnet 4.6",
        }[self]

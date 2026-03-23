"""Model type definitions."""

from enum import Enum


class ModelType(str, Enum):
    """Supported model types."""

    GPT5 = "gpt5"
    OPUS = "opus"

    @property
    def model_name(self) -> str:
        """Get the actual model identifier."""
        if self == ModelType.GPT5:
            return "openai/gpt-5.4"
        elif self == ModelType.OPUS:
            return "anthropic/claude-opus-4.6"
        else:
            raise ValueError(f"Unknown model type: {self}")

    @property
    def display_name(self) -> str:
        """Get display name for the model."""
        if self == ModelType.GPT5:
            return "GPT-5.4"
        elif self == ModelType.OPUS:
            return "Claude Opus 4.6"
        else:
            return str(self.value)

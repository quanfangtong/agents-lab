"""LLM client for interacting with OpenRouter models."""

import os
from typing import Optional, List, Dict, Any
from openai import OpenAI
from loguru import logger
from dotenv import load_dotenv

from .models import ModelType

# Load environment variables
load_dotenv()


class LLMClient:
    """Client for interacting with LLM models via OpenRouter."""

    def __init__(self):
        """Initialize LLM client with OpenRouter configuration."""
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        logger.info("Initialized LLMClient with OpenRouter")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: ModelType = ModelType.GPT5,
        temperature: float = 0.0,
        max_tokens: Optional[int] = 16000,
        timeout: Optional[int] = 120,
        reasoning: bool = True,
        **kwargs,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model type to use
            temperature: Sampling temperature (0 for deterministic SQL generation)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds (default 120)
            reasoning: Enable extended thinking/reasoning (default True)
            **kwargs: Additional parameters for the API

        Returns:
            Generated text response
        """
        try:
            extra_body = kwargs.pop("extra_body", {})

            if reasoning:
                if model in (ModelType.GPT5, ModelType.GPT5_MINI):
                    extra_body["reasoning"] = {"effort": "high"}
                elif model in (ModelType.OPUS, ModelType.SONNET):
                    extra_body["reasoning"] = {
                        "type": "enabled",
                        "budget_tokens": 32000,
                    }

            response = self.client.chat.completions.create(
                model=model.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=float(timeout),
                extra_body=extra_body if extra_body else None,
                **kwargs,
            )

            content = response.choices[0].message.content
            logger.info(
                f"Chat completion successful with {model.display_name}: "
                f"{response.usage.total_tokens} tokens"
            )

            return content

        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise

    def simple_query(
        self,
        prompt: str,
        model: ModelType = ModelType.GPT5,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = 16000,
    ) -> str:
        """
        Send a simple query with optional system prompt.

        Args:
            prompt: User prompt
            model: Model type to use
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0 for SQL generation)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def batch_query(
        self,
        prompts: List[str],
        model: ModelType = ModelType.GPT5,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> List[str]:
        """
        Send multiple queries and collect responses.

        Args:
            prompts: List of user prompts
            model: Model type to use
            system_prompt: Optional system prompt
            temperature: Sampling temperature

        Returns:
            List of generated responses
        """
        responses = []

        for i, prompt in enumerate(prompts):
            logger.info(f"Processing batch query {i + 1}/{len(prompts)}")
            response = self.simple_query(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
            )
            responses.append(response)

        return responses


# Global instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client

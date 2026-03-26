"""LLM client supporting Azure OpenAI and OpenRouter."""

import os
import time
import threading
from typing import Optional, List, Dict
from openai import AzureOpenAI, OpenAI
from loguru import logger
from dotenv import load_dotenv

from .models import ModelType

load_dotenv()


class LLMClient:
    """Unified LLM client: Azure OpenAI (primary) with OpenRouter fallback."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "azure")

        if self.provider == "azure":
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_KEY")
            if not endpoint or not api_key:
                raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set in environment")
            self.client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=os.getenv("AZURE_API_VERSION", "2025-04-01-preview"),
            )
            logger.info("Initialized LLMClient with Azure OpenAI")
        else:
            api_key = os.getenv("OPENROUTER_API_KEY")
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not found")
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info("Initialized LLMClient with OpenRouter")

    def _get_deployment_name(self, model: ModelType) -> str:
        """Map ModelType to Azure deployment name."""
        if self.provider == "azure":
            return {
                ModelType.GPT5: "gpt-5.4",
                ModelType.GPT5_MINI: "gpt-5.4",  # Azure 只有 gpt-5.4
                ModelType.OPUS: "gpt-5.4",
                ModelType.SONNET: "gpt-5.4",
            }.get(model, "gpt-5.4")
        else:
            return model.model_name

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: ModelType = ModelType.GPT5,
        temperature: float = 0.0,
        max_tokens: Optional[int] = 16000,
        timeout: Optional[int] = 300,
        reasoning: bool = True,
        max_retries: int = 5,
        **kwargs,
    ) -> str:
        deployment = self._get_deployment_name(model)
        last_error = None

        for attempt in range(max_retries):
            try:
                if self.provider == "azure":
                    input_text = ""
                    for msg in messages:
                        role = msg["role"]
                        content = msg["content"]
                        if role == "system":
                            input_text += f"[System]\n{content}\n\n"
                        elif role == "user":
                            input_text += f"[User]\n{content}\n\n"

                    params = {
                        "model": deployment,
                        "input": input_text,
                        "max_output_tokens": max_tokens,
                    }
                    if reasoning:
                        params["reasoning"] = {"effort": "high"}

                    response = self.client.responses.create(**params)
                    content = response.output_text
                    tokens = getattr(response.usage, 'total_tokens', 0) if response.usage else 0

                else:
                    extra_body = kwargs.pop("extra_body", {})
                    if reasoning:
                        if model in (ModelType.GPT5, ModelType.GPT5_MINI):
                            extra_body["reasoning"] = {"effort": "high"}
                        elif model in (ModelType.OPUS, ModelType.SONNET):
                            extra_body["reasoning"] = {"type": "enabled", "budget_tokens": 32000}

                    response = self.client.chat.completions.create(
                        model=deployment,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=float(timeout),
                        extra_body=extra_body if extra_body else None,
                        **kwargs,
                    )
                    content = response.choices[0].message.content
                    tokens = response.usage.total_tokens if response.usage else 0

                logger.info(f"Chat completion successful with {model.display_name}: {tokens} tokens")
                return content

            except Exception as e:
                last_error = e
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str or "rate" in err_str.lower():
                    wait = min(2 ** attempt * 5, 60)  # 5s, 10s, 20s, 40s, 60s
                    logger.warning(f"Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    if attempt < max_retries - 1:
                        logger.warning(f"Timeout (attempt {attempt+1}/{max_retries}), retrying...")
                        time.sleep(2)
                        continue
                # Non-retryable error
                logger.error(f"Chat completion failed: {e}")
                raise

        logger.error(f"Chat completion failed after {max_retries} retries: {last_error}")
        raise last_error

    def simple_query(
        self,
        prompt: str,
        model: ModelType = ModelType.GPT5,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = 16000,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat_completion(messages=messages, model=model, temperature=temperature, max_tokens=max_tokens)


# Thread-safe global instance
_llm_client: Optional[LLMClient] = None
_llm_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        with _llm_lock:
            if _llm_client is None:
                _llm_client = LLMClient()
    return _llm_client

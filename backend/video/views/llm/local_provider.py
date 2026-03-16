import openai
import httpx
from typing import List, Optional, Union

from .base import BaseProvider, ChatResponse, TokenUsage, Message


class LocalProvider(BaseProvider):
    provider_name = "local"

    def __init__(
        self,
        api_key: str = "dummy",
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(api_key, base_url, default_model, **kwargs)

        if not self.base_url:
            raise ValueError(
                "LocalProvider requires base_url (e.g., http://localhost:1234/v1 for LM Studio, "
                "or http://localhost:11434/v1 for Ollama)"
            )
        if not self.default_model:
            raise ValueError(
                "LocalProvider requires default_model (e.g., llama3.1, gpt-oss-20b-mxfp4, qwen2.5)"
            )

    def _create_client(self):
        http_client = httpx.Client(proxy=None, timeout=120, trust_env=False)
        return openai.OpenAI(
            api_key=self.api_key, base_url=self.base_url, http_client=http_client
        )

    @property
    def supports_temperature(self) -> bool:
        return True

    @property
    def supports_max_tokens(self) -> bool:
        return True

    @property
    def available_models(self) -> List[str]:
        return []

    def chat(
        self,
        messages: List[Union[Message, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        selected_model = model or self.default_model

        if not selected_model:
            raise ValueError("No model specified for LocalProvider")

        normalized_messages = self.normalize_messages(messages)

        request_params = {
            "model": selected_model,
            "messages": normalized_messages,
        }

        if temperature is not None:
            request_params["temperature"] = temperature

        if max_tokens is not None:
            request_params["max_tokens"] = max_tokens

        request_params.update(kwargs)

        response = self.client.chat.completions.create(**request_params)

        usage = TokenUsage.from_response(
            {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens
                if response.usage
                else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
        )

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        finish_reason = choice.finish_reason if choice else None

        return ChatResponse(
            content=content,
            model=selected_model,
            usage=usage,
            finish_reason=finish_reason,
            raw_response=response,
        )

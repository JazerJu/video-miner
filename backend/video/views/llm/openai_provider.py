import openai
from typing import List, Optional, Dict, Any, Union

from .base import BaseProvider, ChatResponse, TokenUsage, Message


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(api_key, base_url, default_model, **kwargs)

        if not self.default_model:
            self.default_model = "gpt-4o"

    def _create_client(self):
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        return openai.OpenAI(**client_kwargs)

    @property
    def supports_temperature(self) -> bool:
        model = self.default_model or ""
        return not model.startswith("o1") and not model.startswith("o3")

    @property
    def supports_max_tokens(self) -> bool:
        return True

    @property
    def available_models(self) -> List[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3-mini",
            "o4-mini",
        ]

    def chat(
        self,
        messages: List[Union[Message, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        selected_model = self.validate_model(model)

        normalized_messages = self.normalize_messages(messages)

        request_params = {
            "model": selected_model,
            "messages": normalized_messages,
        }

        if temperature is not None and self.supports_temperature:
            request_params["temperature"] = temperature

        if max_tokens is not None:
            if selected_model.startswith(("o1", "o3")):
                request_params["max_completion_tokens"] = max_tokens
            else:
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

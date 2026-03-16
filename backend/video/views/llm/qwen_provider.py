import openai
from typing import List, Optional, Union

from .base import BaseProvider, ChatResponse, TokenUsage, Message


class QwenProvider(BaseProvider):
    provider_name = "qwen"

    THINKING_MODELS = {
        "qwen3-235b-a22b-instruct-2507": "qwen3-235b-a22b-thinking-2507",
        "qwen3-235b-a22b-thinking-2507": "qwen3-235b-a22b-thinking-2507",
    }

    DEFAULT_MODELS = {
        "normal": "qwen3-235b-a22b-instruct-2507",
        "thinking": "qwen3-235b-a22b-thinking-2507",
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model: Optional[str] = None,
        enable_thinking: bool = False,
        **kwargs,
    ):
        super().__init__(api_key, base_url, default_model, enable_thinking, **kwargs)

        if not self.default_model:
            self.default_model = (
                self.DEFAULT_MODELS["thinking"]
                if self.enable_thinking
                else self.DEFAULT_MODELS["normal"]
            )

    def _create_client(self):
        return openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    @property
    def supports_thinking(self) -> bool:
        return True

    @property
    def supports_temperature(self) -> bool:
        return True

    @property
    def supports_max_tokens(self) -> bool:
        return True

    @property
    def available_models(self) -> List[str]:
        return [
            "qwen3-235b-a22b-instruct-2507",
            "qwen3-235b-a22b-thinking-2507",
            "qwen-max",
            "qwen-plus",
            "qwen-turbo",
        ]

    def get_thinking_model(self, base_model: str) -> str:
        if self.enable_thinking:
            if base_model in self.THINKING_MODELS:
                return self.THINKING_MODELS[base_model]
            return self.DEFAULT_MODELS["thinking"]
        return base_model

    def chat(
        self,
        messages: List[Union[Message, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enable_thinking: Optional[bool] = None,
        **kwargs,
    ) -> ChatResponse:
        selected_model = self.validate_model(model)

        thinking_mode = (
            enable_thinking if enable_thinking is not None else self.enable_thinking
        )
        if thinking_mode:
            selected_model = self.get_thinking_model(selected_model)

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

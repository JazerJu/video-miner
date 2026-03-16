import os
import sys
from pathlib import Path
from typing import Dict, Optional, Type, Any

from .base import BaseProvider
from .openai_provider import OpenAIProvider
from .deepseek_provider import DeepSeekProvider
from .chatglm_provider import ChatGLMProvider
from .qwen_provider import QwenProvider
from .local_provider import LocalProvider


_PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "chatglm": ChatGLMProvider,
    "qwen": QwenProvider,
    "local": LocalProvider,
}


class ProviderFactory:
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseProvider]) -> None:
        _PROVIDER_REGISTRY[name] = provider_class

    @classmethod
    def list_providers(cls) -> list:
        return list(_PROVIDER_REGISTRY.keys())

    @classmethod
    def get_provider(
        cls, provider_name: str, config: Optional[Dict[str, Any]] = None, **kwargs
    ) -> BaseProvider:
        if provider_name not in _PROVIDER_REGISTRY:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {cls.list_providers()}"
            )

        provider_class = _PROVIDER_REGISTRY[provider_name]

        merged_kwargs = {}
        if config:
            merged_kwargs.update(config)
        merged_kwargs.update(kwargs)

        return provider_class(**merged_kwargs)

    @classmethod
    def get_provider_from_config(
        cls, provider_name: str, config_path: Optional[str] = None
    ) -> BaseProvider:
        from .config import load_provider_config

        config = load_provider_config(provider_name, config_path)
        return cls.get_provider(provider_name, config)

    @classmethod
    def is_registered(cls, provider_name: str) -> bool:
        return provider_name in _PROVIDER_REGISTRY


def get_default_provider(config_path: Optional[str] = None) -> BaseProvider:
    from .config import get_default_provider_name

    provider_name = get_default_provider_name(config_path)
    return ProviderFactory.get_provider_from_config(provider_name, config_path)

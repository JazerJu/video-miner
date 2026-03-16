"""LLM Provider Base Classes

Defines the abstract base class and data structures for all LLM providers.
All provider implementations must inherit from BaseProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union
from enum import Enum


class MessageRole(str, Enum):
    """Standard message roles for chat conversations."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Represents a single message in a conversation."""

    role: MessageRole
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format for API calls."""
        result = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


@dataclass
class TokenUsage:
    """Token usage statistics for a chat completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @classmethod
    def from_response(cls, usage_data: Dict[str, int]) -> "TokenUsage":
        """Create TokenUsage from API response data."""
        return cls(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )


@dataclass
class ChatResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    usage: TokenUsage
    finish_reason: Optional[str] = None
    raw_response: Optional[Any] = None  # Provider-specific raw response

    @property
    def reasoning_content(self) -> Optional[str]:
        """Optional reasoning/thinking content from models that support it."""
        if self.raw_response and hasattr(self.raw_response, "choices"):
            choice = self.raw_response.choices[0] if self.raw_response.choices else None
            if choice and hasattr(choice.message, "reasoning_content"):
                return choice.message.reasoning_content
        return None


class BaseProvider(ABC):
    """Abstract base class for all LLM providers.

    All provider implementations must inherit from this class and implement
    the abstract methods. This ensures a consistent interface across
    different LLM services.

    Example:
        >>> class MyProvider(BaseProvider):
        ...     provider_name = "my_provider"
        ...
        ...     def chat(self, messages, **kwargs):
        ...         # Implementation
        ...         pass
    """

    provider_name: str = ""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        **kwargs,
    ):
        """Initialize the provider with configuration.

        Args:
            api_key: API key for authentication
            base_url: Custom base URL for the API (optional)
            default_model: Default model to use if none specified
            **kwargs: Additional provider-specific parameters
        """
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self._client = None

    @property
    def client(self):
        """Lazy initialization of the HTTP client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @abstractmethod
    def _create_client(self):
        """Create and return the provider-specific HTTP client.

        This method should create the actual client instance (e.g., OpenAI client,
        httpx session, etc.) that will be used for API calls.
        """
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Union[Message, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        """Execute a chat completion request.

        Args:
            messages: List of messages (Message objects or dicts with role/content)
            model: Model to use (defaults to self.default_model)
            temperature: Sampling temperature (if supported)
            max_tokens: Maximum tokens to generate (if supported)
            **kwargs: Additional provider-specific parameters

        Returns:
            ChatResponse with standardized response data
        """
        pass

    @property
    @abstractmethod
    def supports_temperature(self) -> bool:
        """Whether this provider supports temperature parameter."""
        pass

    @property
    @abstractmethod
    def supports_max_tokens(self) -> bool:
        """Whether this provider supports max_tokens parameter."""
        pass

    @property
    @abstractmethod
    def available_models(self) -> List[str]:
        """List of available models for this provider.

        Returns:
            List of model identifiers supported by this provider.
        """
        pass

    def normalize_messages(
        self, messages: List[Union[Message, Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """Normalize messages to a standard dictionary format.

        Args:
            messages: List of Message objects or dicts

        Returns:
            List of standardized message dictionaries
        """
        normalized = []
        for msg in messages:
            if isinstance(msg, Message):
                normalized.append(msg.to_dict())
            elif isinstance(msg, dict):
                normalized.append(msg)
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")
        return normalized

    def validate_model(self, model: Optional[str]) -> str:
        """Validate and return the model to use.

        Args:
            model: Requested model name (optional)

        Returns:
            Validated model name

        Raises:
            ValueError: If no model is specified and no default exists
        """
        selected = model or self.default_model
        if not selected:
            raise ValueError(
                f"No model specified for {self.provider_name}. "
                "Provide a model name or set default_model."
            )
        return selected

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"provider='{self.provider_name}', "
            f"model='{self.default_model}'"
            f")"
        )

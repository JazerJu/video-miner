from typing import Optional, Dict, Any
import httpx


PROVIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    'ollama': {
        'url': 'http://127.0.0.1:11434',
        'sdk': 'ollama',
        'default_model': 'llama3',
    },
    'lmstudio': {
        'url': 'http://127.0.0.1:1234/v1',
        'sdk': 'openai',
        'default_model': '',
    },
    'openai': {
        'url': 'https://api.openai.com/v1',
        'sdk': 'openai',
        'default_model': 'gpt-4o',
    },
    'deepseek': {
        'url': 'https://api.deepseek.com/v1',
        'sdk': 'openai',
        'default_model': 'deepseek-chat',
    },
    'moonshot': {
        'url': 'https://api.moonshot.cn/v1',
        'sdk': 'openai',
        'default_model': 'moonshot-v1-8k',
    },
    'zhipu': {
        'url': 'https://open.bigmodel.cn/api/paas/v4',
        'sdk': 'openai',
        'default_model': 'glm-4-plus',
    },
    'qwen': {
        'url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'sdk': 'openai',
        'default_model': 'qwen-plus',
    },
    'cerebras': {
        'url': 'https://api.cerebras.ai/v1',
        'sdk': 'openai',
        'default_model': 'llama3.1-8b',
    },
    'local': {
        'url': 'http://localhost:1234/v1',
        'sdk': 'openai',
        'default_model': '',
    },
}

DEFAULT_TIMEOUTS: Dict[str, float] = {
    'ollama': 60.0,
    'lmstudio': 60.0,
    'openai': 30.0,
    'deepseek': 30.0,
    'moonshot': 30.0,
    'zhipu': 30.0,
    'qwen': 30.0,
    'cerebras': 30.0,
    'volcano': 30.0,
    'openrouter': 30.0,
    'local': 60.0,
}

DEFAULT_TIMEOUT = 30.0


class ClientPool:
    _cache: Dict[str, Any] = {}
    
    @classmethod
    def get_client(
        cls,
        provider: str,
        api_key: str = '',
        base_url: str = '',
        use_proxy: bool = False,
        proxy_url: str = '',
    ) -> Any:
        cache_key = f"{provider}_{base_url}"
        
        if cache_key not in cls._cache:
            defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS['local'])
            
            url = base_url or defaults['url']
            key = api_key or 'dummy-key'
            timeout = DEFAULT_TIMEOUTS.get(provider, DEFAULT_TIMEOUT)
            
            if defaults['sdk'] == 'ollama':
                cls._cache[cache_key] = cls._create_ollama_client(url, timeout)
            else:
                cls._cache[cache_key] = cls._create_openai_client(
                    key, url, timeout, use_proxy, proxy_url
                )
        
        return cls._cache[cache_key]
    
    @classmethod
    def _create_ollama_client(cls, host: str, timeout: float) -> Any:
        try:
            from ollama import Client
            return Client(host=host, timeout=timeout)
        except ImportError:
            raise ImportError(
                "请安装 ollama 包: pip install ollama\n"
                "或者使用 OpenAI 兼容模式，将 base_url 设置为 http://localhost:11434/v1"
            )
    
    @classmethod
    def _create_openai_client(
        cls,
        api_key: str,
        base_url: str,
        timeout: float,
        use_proxy: bool = False,
        proxy_url: str = '',
    ) -> Any:
        from openai import OpenAI
        
        http_client = None
        if use_proxy and proxy_url:
            http_client = httpx.Client(proxy=proxy_url, timeout=timeout)
        elif not use_proxy:
            http_client = httpx.Client(proxy=None, timeout=timeout, trust_env=False)
        
        kwargs = {
            'api_key': api_key,
            'base_url': base_url,
        }
        if http_client:
            kwargs['http_client'] = http_client
        
        return OpenAI(**kwargs)
    
    @classmethod
    def clear(cls):
        cls._cache.clear()
    
    @classmethod
    def get_provider_info(cls, provider: str) -> Dict[str, Any]:
        return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS['local'])
    
    @classmethod
    def list_providers(cls) -> list:
        return list(PROVIDER_DEFAULTS.keys())


def get_client_from_settings(
    settings: Dict[str, Any],
    prefix: str = '',
    use_proxy_key: str = 'split_use_proxy',
) -> Any:
    default_cfg = settings.get('DEFAULT', {})
    
    provider_key = f'{prefix}selected_model_provider' if prefix else 'selected_model_provider'
    provider = default_cfg.get(provider_key, 'deepseek')
    
    api_key = default_cfg.get(f'{prefix}{provider}_api_key', '')
    base_url = default_cfg.get(f'{prefix}{provider}_base_url', '')
    
    use_proxy = default_cfg.get(use_proxy_key, 'false').lower() == 'true'
    proxy_url = default_cfg.get('proxy_url', '')
    
    return ClientPool.get_client(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        use_proxy=use_proxy,
        proxy_url=proxy_url,
    )

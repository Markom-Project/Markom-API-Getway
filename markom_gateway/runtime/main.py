import json
import os
from typing import Final

from pydantic import TypeAdapter

from .app import create_app
from .openrouter import OpenRouterProvider
from .providers import OpenAICompatibleProvider
from .routing import ModelRoute, ModelRouter

_api_key: Final[str] = os.environ.get("MARKOM_MASTER_KEY", "")
_openrouter_api_key: Final[str] = os.environ.get("OPENROUTER_API_KEY", "")
_openrouter_base_url: Final[str] = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
_model_routes_json: Final[str] = os.environ.get("MARKOM_MODEL_ROUTES", "{}")
_openai_api_key: Final[str] = os.environ.get("OPENAI_API_KEY", "")
_openai_base_url: Final[str] = os.environ.get(
    "OPENAI_BASE_URL", "https://api.openai.com/v1"
)
_model_routes: Final[dict[str, ModelRoute]] = TypeAdapter(
    dict[str, ModelRoute]
).validate_python(json.loads(_model_routes_json))
_providers: Final[dict[str, OpenRouterProvider | OpenAICompatibleProvider]] = {
    "openrouter": OpenRouterProvider(
        api_key=_openrouter_api_key,
        base_url=_openrouter_base_url,
    )
} | (
    {
        "openai": OpenAICompatibleProvider(
            api_key=_openai_api_key,
            base_url=_openai_base_url,
        )
    }
    if _openai_api_key
    else {}
)

app = create_app(
    provider=ModelRouter(
        providers=_providers,
        default_provider="openrouter",
        routes=_model_routes,
    ),
    api_key=_api_key,
)

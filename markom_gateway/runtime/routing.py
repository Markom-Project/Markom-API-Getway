import asyncio
from types import MappingProxyType
from typing import Final, Mapping

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .app import CompletionProvider


class ModelTarget(BaseModel):
    provider: str
    model: str

    model_config = ConfigDict(frozen=True)


class ModelRoute(BaseModel):
    targets: tuple[ModelTarget, ...] = Field(min_length=1)

    model_config = ConfigDict(frozen=True)


class ModelRouter:
    def __init__(
        self,
        providers: Mapping[str, CompletionProvider],
        default_provider: str,
        routes: Mapping[str, ModelRoute],
    ) -> None:
        if default_provider not in providers:
            raise ValueError(f"Unknown default provider: {default_provider}")
        unknown_providers: Final[frozenset[str]] = frozenset(
            target.provider
            for route in routes.values()
            for target in route.targets
            if target.provider not in providers
        )
        if unknown_providers:
            raise ValueError(
                f"Model routes reference unknown providers: {', '.join(sorted(unknown_providers))}"
            )
        self._providers: Final[Mapping[str, CompletionProvider]] = MappingProxyType(
            dict(providers)
        )
        self._default_provider: Final[str] = default_provider
        self._routes: Final[Mapping[str, ModelRoute]] = MappingProxyType(dict(routes))

    async def chat_completions(
        self, payload: dict[str, object], *, stream: bool
    ) -> httpx.Response:
        model: Final[str] = str(payload["model"])
        route: Final[ModelRoute | None] = self._routes.get(model)
        if route is None:
            return await self._providers[self._default_provider].chat_completions(
                payload, stream=stream
            )
        return await self._complete(route.targets, payload, stream)

    async def _complete(
        self,
        targets: tuple[ModelTarget, ...],
        payload: dict[str, object],
        stream: bool,
    ) -> httpx.Response:
        target: Final[ModelTarget] = targets[0]
        provider: Final[CompletionProvider] = self._providers[target.provider]
        routed_payload: Final[dict[str, object]] = payload | {"model": target.model}
        try:
            response: Final[httpx.Response] = await provider.chat_completions(
                routed_payload, stream=stream
            )
        except httpx.RequestError:
            if len(targets) == 1:
                raise
            return await self._complete(targets[1:], payload, stream)
        if response.status_code not in (429,) and response.status_code < 500:
            return response
        if len(targets) == 1:
            return response
        await response.aclose()
        return await self._complete(targets[1:], payload, stream)

    async def list_models(self) -> httpx.Response:
        if not self._routes:
            return await self._providers[self._default_provider].list_models()
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": model, "object": "model"}
                    for model in sorted(self._routes)
                ],
            },
        )

    async def aclose(self) -> None:
        await asyncio.gather(
            *(provider.aclose() for provider in self._providers.values())
        )

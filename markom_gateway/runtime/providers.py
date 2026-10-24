from typing import Final

import httpx


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Provider API key must be configured")
        self._api_key: Final[str] = api_key
        self._client: Final[httpx.AsyncClient] = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=120.0,
        )

    async def chat_completions(
        self, payload: dict[str, object], *, stream: bool
    ) -> httpx.Response:
        request: Final[httpx.Request] = self._client.build_request(
            "POST",
            "/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
        )
        return await self._client.send(request, stream=stream)

    async def list_models(self) -> httpx.Response:
        return await self._client.get(
            "/models",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

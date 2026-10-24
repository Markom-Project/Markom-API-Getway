import asyncio
import json
from collections.abc import AsyncIterator
from typing import Final

import httpx
from fastapi.testclient import TestClient

from markom_gateway.runtime.app import create_app
from markom_gateway.runtime.openrouter import OpenRouterProvider
from markom_gateway.runtime.providers import OpenAICompatibleProvider
from markom_gateway.runtime.routing import ModelRoute, ModelRouter, ModelTarget


class EventStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        return None


class FakeProvider:
    def __init__(self) -> None:
        self.chat_payload: dict[str, object] | None = None
        self.stream: bool | None = None
        self.closed = False

    async def chat_completions(
        self, payload: dict[str, object], *, stream: bool
    ) -> httpx.Response:
        self.chat_payload = payload
        self.stream = stream
        if stream:
            return httpx.Response(
                200,
                stream=EventStream(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "Hello"}}],
            },
        )

    async def list_models(self) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-4o-mini"}]})

    async def aclose(self) -> None:
        self.closed = True


class RoutedFakeProvider:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.models: list[str] = []

    async def chat_completions(
        self, payload: dict[str, object], *, stream: bool
    ) -> httpx.Response:
        self.models.append(str(payload["model"]))
        return self.response

    async def list_models(self) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    async def aclose(self) -> None:
        return None


def test_chat_completion_forwards_openai_compatible_body() -> None:
    provider: Final[FakeProvider] = FakeProvider()
    app = create_app(provider, "gateway-secret")

    with TestClient(app) as client:
        response: Final[httpx.Response] = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer gateway-secret"},
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.2,
                "stream": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello"
    assert provider.chat_payload == {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.2,
        "stream": False,
    }
    assert provider.stream is False
    assert provider.closed


def test_chat_completion_rejects_missing_or_invalid_api_key() -> None:
    provider: Final[FakeProvider] = FakeProvider()
    app = create_app(provider, "gateway-secret")

    with TestClient(app) as client:
        missing: Final[httpx.Response] = client.post(
            "/v1/chat/completions",
            json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user"}]},
        )
        invalid: Final[httpx.Response] = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer incorrect"},
            json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user"}]},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert provider.chat_payload is None


def test_streaming_response_is_forwarded_as_server_sent_events() -> None:
    provider: Final[FakeProvider] = FakeProvider()
    app = create_app(provider, "gateway-secret")

    with TestClient(app) as client:
        response: Final[httpx.Response] = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer gateway-secret"},
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in response.text
    assert provider.stream is True


def test_models_endpoint_requires_authentication() -> None:
    provider: Final[FakeProvider] = FakeProvider()
    app = create_app(provider, "gateway-secret")

    with TestClient(app) as client:
        unauthorized: Final[httpx.Response] = client.get("/v1/models")
        response: Final[httpx.Response] = client.get(
            "/v1/models",
            headers={"Authorization": "Bearer gateway-secret"},
        )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "openai/gpt-4o-mini"


def test_openrouter_provider_uses_openai_compatible_upstream_paths() -> None:
    requests: Final[list[httpx.Request]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": []})

    client: Final[httpx.AsyncClient] = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1",
        transport=httpx.MockTransport(handle),
    )
    provider: Final[OpenRouterProvider] = OpenRouterProvider(
        api_key="upstream-secret",
        base_url="https://openrouter.test/api/v1",
        client=client,
    )

    async def call_provider() -> None:
        chat: Final[httpx.Response] = await provider.chat_completions(
            {
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            stream=False,
        )
        models: Final[httpx.Response] = await provider.list_models()
        await chat.aread()
        await models.aread()

    import asyncio

    asyncio.run(call_provider())

    assert [request.url.path for request in requests] == [
        "/api/v1/chat/completions",
        "/api/v1/models",
    ]
    assert all(
        request.headers["authorization"] == "Bearer upstream-secret"
        for request in requests
    )
    assert json.loads(requests[0].content)["model"] == "openai/gpt-4o-mini"


def test_model_router_uses_fallback_for_upstream_server_error() -> None:
    primary: Final[RoutedFakeProvider] = RoutedFakeProvider(
        httpx.Response(503, json={"error": "unavailable"})
    )
    fallback: Final[RoutedFakeProvider] = RoutedFakeProvider(
        httpx.Response(200, json={"choices": []})
    )
    router: Final[ModelRouter] = ModelRouter(
        providers={"primary": primary, "fallback": fallback},
        default_provider="primary",
        routes={
            "chat-model": ModelRoute(
                targets=(
                    ModelTarget(provider="primary", model="model-a"),
                    ModelTarget(provider="fallback", model="model-b"),
                )
            )
        },
    )

    async def call_router() -> httpx.Response:
        return await router.chat_completions(
            {"model": "chat-model", "messages": [{"role": "user", "content": "Hi"}]},
            stream=False,
        )

    response: Final[httpx.Response] = asyncio.run(call_router())

    assert response.status_code == 200
    assert primary.models == ["model-a"]
    assert fallback.models == ["model-b"]


def test_model_router_does_not_fallback_for_client_errors() -> None:
    primary: Final[RoutedFakeProvider] = RoutedFakeProvider(
        httpx.Response(400, json={"error": "invalid request"})
    )
    fallback: Final[RoutedFakeProvider] = RoutedFakeProvider(
        httpx.Response(200, json={"choices": []})
    )
    router: Final[ModelRouter] = ModelRouter(
        providers={"primary": primary, "fallback": fallback},
        default_provider="primary",
        routes={
            "chat-model": ModelRoute(
                targets=(
                    ModelTarget(provider="primary", model="model-a"),
                    ModelTarget(provider="fallback", model="model-b"),
                )
            )
        },
    )

    async def call_router() -> httpx.Response:
        return await router.chat_completions(
            {"model": "chat-model", "messages": [{"role": "user", "content": "Hi"}]},
            stream=False,
        )

    response: Final[httpx.Response] = asyncio.run(call_router())

    assert response.status_code == 400
    assert primary.models == ["model-a"]
    assert fallback.models == []


def test_model_router_lists_configured_virtual_models() -> None:
    provider: Final[RoutedFakeProvider] = RoutedFakeProvider(httpx.Response(200))
    router: Final[ModelRouter] = ModelRouter(
        providers={"primary": provider},
        default_provider="primary",
        routes={
            "chat-model": ModelRoute(
                targets=(ModelTarget(provider="primary", model="provider-model"),)
            )
        },
    )

    async def list_models() -> httpx.Response:
        return await router.list_models()

    response: Final[httpx.Response] = asyncio.run(list_models())

    assert response.json() == {
        "object": "list",
        "data": [{"id": "chat-model", "object": "model"}],
    }


def test_openai_compatible_provider_uses_configured_endpoint() -> None:
    requests: Final[list[httpx.Request]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": []})

    client: Final[httpx.AsyncClient] = httpx.AsyncClient(
        base_url="https://openai-compatible.test/v1",
        transport=httpx.MockTransport(handle),
    )
    provider: Final[OpenAICompatibleProvider] = OpenAICompatibleProvider(
        api_key="provider-secret",
        base_url="https://openai-compatible.test/v1",
        client=client,
    )

    async def call_provider() -> httpx.Response:
        return await provider.chat_completions(
            {"model": "model-a", "messages": [{"role": "user", "content": "Hi"}]},
            stream=False,
        )

    response: Final[httpx.Response] = asyncio.run(call_provider())

    assert response.status_code == 200
    assert requests[0].url.path == "/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer provider-secret"
    assert json.loads(requests[0].content)["model"] == "model-a"

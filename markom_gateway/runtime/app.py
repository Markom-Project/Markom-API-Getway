import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final, Protocol

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, object]] = Field(min_length=1)
    stream: bool = False

    model_config = ConfigDict(extra="allow")


class CompletionProvider(Protocol):
    async def chat_completions(
        self, payload: dict[str, object], *, stream: bool
    ) -> httpx.Response: ...

    async def list_models(self) -> httpx.Response: ...

    async def aclose(self) -> None: ...


async def _response(upstream: httpx.Response) -> Response:
    content: Final[bytes] = await upstream.aread()
    content_type: Final[str | None] = upstream.headers.get("content-type")
    await upstream.aclose()
    return Response(
        content=content,
        status_code=upstream.status_code,
        media_type=content_type,
    )


def _stream_response(upstream: httpx.Response) -> StreamingResponse:
    content_type: Final[str | None] = upstream.headers.get("content-type")
    return StreamingResponse(
        upstream.aiter_bytes(),
        status_code=upstream.status_code,
        media_type=content_type,
        background=BackgroundTask(upstream.aclose),
    )


def create_app(provider: CompletionProvider, api_key: str) -> FastAPI:
    if not api_key:
        raise ValueError("MARKOM_MASTER_KEY must be configured")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await provider.aclose()

    app: Final[FastAPI] = FastAPI(
        title="MarKom Gateway",
        version="0.1.0",
        lifespan=lifespan,
    )

    async def authenticate(authorization: str | None) -> None:
        expected: Final[str] = f"Bearer {api_key}"
        if authorization is None or not hmac.compare_digest(
            authorization.encode("utf-8"), expected.encode("utf-8")
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def list_models(authorization: str | None = Header(default=None)) -> Response:
        await authenticate(authorization)
        try:
            upstream: Final[httpx.Response] = await provider.list_models()
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Upstream provider request failed",
            ) from exc
        return await _response(upstream)

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
    ) -> Response:
        await authenticate(authorization)
        payload: Final[dict[str, object]] = request.model_dump(
            mode="json", exclude_unset=True
        )
        try:
            upstream: Final[httpx.Response] = await provider.chat_completions(
                payload, stream=request.stream
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Upstream provider request failed",
            ) from exc
        if request.stream and upstream.is_success:
            return _stream_response(upstream)
        return await _response(upstream)

    return app

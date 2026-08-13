"""FastAPI/Uvicorn loopback server facade (slice-00-05, ADR-0028).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

Thin framework adapter over the pure protocol layer in ``_protocol.py``.
FastAPI/Uvicorn are imported lazily here and exist only inside the
ADR-0028-authorized Managed Runtime; the dev environment never imports
this module, and a stdlib HTTP server is not an equivalent substitute for
the ADR-0022 FastAPI/Uvicorn choice. The module is excluded from strict
pyright analysis because the framework packages are not part of the root
dev environment.
"""

# pyright: basic
# pyright: ignore[reportMissingImports]
# NOTE: no ``from __future__ import annotations`` here on purpose. The
# endpoint annotation ``request: Request`` must evaluate to the real class
# at definition time (inside create_app, where the lazy import lives);
# FastAPI resolves dependency-injected parameters by type, and a string
# annotation would fall back to treating ``request`` as a query parameter.
from typing import Any

from ._constants import BODY_LIMIT_BYTES
from ._protocol import RequestContext, ServerState, validate_and_handle


async def _read_bounded(request: Any) -> bytes:
    """Read the request body with a hard cap (413 handled by the protocol).

    Chunks are appended before the size check so an oversize stream is
    never silently truncated below the limit (a truncated body would fail
    JSON parsing with 400 instead of the fixed 413).
    """
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        chunks.append(chunk)
        size += len(chunk)
        if size > BODY_LIMIT_BYTES:
            break
    return b"".join(chunks)


def create_app(state: ServerState) -> Any:
    """Build the FastAPI application bound to one ServerState."""
    from fastapi import (  # pyright: ignore[reportMissingImports] - managed runtime only
        FastAPI,
        Request,
    )
    from fastapi.responses import JSONResponse  # pyright: ignore[reportMissingImports]

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
    )
    async def dispatch(full_path: str, request: Request) -> JSONResponse:
        del full_path
        body = await _read_bounded(request)
        ctx = RequestContext(
            method=request.method,
            path=request.url.path,
            host=request.headers.get("host", ""),
            origin=request.headers.get("origin"),
            protocol_header=request.headers.get("X-Hermes-Pipeline-Protocol"),
            authorization=request.headers.get("authorization"),
            body=body,
            now=state.clock(),
        )
        result = validate_and_handle(ctx, state)
        return JSONResponse(status_code=result.status, content=result.body)

    return app


__all__ = ["create_app"]

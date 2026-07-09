"""Exception handler that renders ApiError as the contract error envelope."""

from __future__ import annotations

from typing import cast

from fastapi import Request
from fastapi.responses import JSONResponse

from src.api.errors import ApiError


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Registered only for ApiError (and subclasses), so the cast always holds.
    err = cast(ApiError, exc)
    return JSONResponse(
        status_code=err.status_code,
        content={"error": {"code": err.code, "message": err.message}},
    )

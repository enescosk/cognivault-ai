from __future__ import annotations

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.observability import current_request_id


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    detail: object | None = None,
) -> JSONResponse:
    request_id = current_request_id() or request.headers.get("X-Request-ID")
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "path": request.url.path,
        }
    }
    if detail is not None:
        payload["error"]["detail"] = jsonable_encoder(detail)
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Request-ID": request_id or ""})

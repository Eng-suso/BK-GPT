from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.schemas.api import ApiEnvelope, ApiError, ApiMeta


REQUEST_ID_HEADER = "X-Request-ID"


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id

    return request.headers.get(REQUEST_ID_HEADER) or str(uuid4())


def _duration_ms(request: Request) -> int | None:
    started_at = getattr(request.state, "started_at", None)
    if started_at is None:
        return None

    return int((perf_counter() - started_at) * 1000)


def _error_code(status_code: int) -> str:
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "validation_error"
    if status_code == 429:
        return "rate_limited"
    if status_code == 503:
        return "service_unavailable"
    return "server_error" if status_code >= 500 else "api_error"


def api_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    detail: str | None = None,
    retryable: bool = False,
) -> JSONResponse:
    request_id = _request_id(request)
    envelope = ApiEnvelope(
        ok=False,
        data=None,
        error=ApiError(
            code=code,
            message=message,
            detail=detail,
            request_id=request_id,
            origin="server",
            retryable=retryable,
        ),
        meta=ApiMeta(
            request_id=request_id,
            duration_ms=_duration_ms(request),
        ),
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={REQUEST_ID_HEADER: request_id},
    )


def setup_api_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        request.state.started_at = perf_counter()

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Richiesta non valida."
        return api_error_response(
            request,
            status_code=exc.status_code,
            code=_error_code(exc.status_code),
            message=message,
            retryable=exc.status_code in {429, 503},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return api_error_response(
            request,
            status_code=422,
            code="validation_error",
            message="La richiesta non rispetta il contratto API.",
            detail=str(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return api_error_response(
            request,
            status_code=500,
            code="server_error",
            message="Errore interno del server.",
            detail=exc.__class__.__name__,
        )

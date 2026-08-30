from __future__ import annotations

import re
from contextvars import ContextVar, Token
from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.settings import settings


TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
DEFAULT_LOCAL_TENANT_ID = "local"
_tenant_id: ContextVar[str | None] = ContextVar("delir_tenant_id", default=None)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthPrincipal(BaseModel):
    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    is_admin: bool = False
    auth_mode: str = "local"


def get_current_tenant_id() -> str:
    return _tenant_id.get() or settings.delir_default_tenant_id or DEFAULT_LOCAL_TENANT_ID


def set_current_tenant_id(tenant_id: str) -> Token[str | None]:
    return _tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token[str | None]) -> None:
    _tenant_id.reset(token)


def normalize_tenant_id(value: str | None) -> str:
    tenant_id = (value or settings.delir_default_tenant_id or DEFAULT_LOCAL_TENANT_ID).strip()
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant non valido.")
    return tenant_id


def allowed_tenant_ids() -> set[str]:
    return {
        item.strip()
        for item in (settings.delir_allowed_tenant_ids or "").split(",")
        if item.strip()
    }


def assert_allowed_tenant(tenant_id: str) -> None:
    allowed = allowed_tenant_ids()
    if allowed and tenant_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant non autorizzato.")


def _configured_api_token() -> str:
    token = (settings.delir_api_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DELIR_API_TOKEN non configurato.",
        )
    return token


def _token_from_credentials(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        return None
    return credentials.credentials


def require_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_delir_tenant_id: str | None = Header(default=None),
    x_delir_user_id: str | None = Header(default=None),
) -> AuthPrincipal:
    tenant_id = normalize_tenant_id(x_delir_tenant_id)
    assert_allowed_tenant(tenant_id)

    if not settings.delir_auth_enabled:
        principal = AuthPrincipal(
            user_id=x_delir_user_id or "local-dev",
            tenant_id=tenant_id,
            is_admin=True,
            auth_mode="local",
        )
        set_current_tenant_id(tenant_id)
        request.state.auth_principal = principal
        return principal

    supplied_token = _token_from_credentials(credentials)
    expected_token = _configured_api_token()
    if not supplied_token or not compare_digest(supplied_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali API mancanti o non valide.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = AuthPrincipal(
        user_id=x_delir_user_id or "api-client",
        tenant_id=tenant_id,
        is_admin=not bool(settings.delir_admin_token),
        auth_mode="bearer",
    )
    set_current_tenant_id(tenant_id)
    request.state.auth_principal = principal
    return principal


def require_admin_principal(
    principal: AuthPrincipal = Depends(require_principal),
    x_delir_admin_token: str | None = Header(default=None),
) -> AuthPrincipal:
    if not settings.delir_auth_enabled:
        return principal.model_copy(update={"is_admin": True})

    admin_token = (settings.delir_admin_token or "").strip()
    if not admin_token:
        return principal.model_copy(update={"is_admin": True})

    if not x_delir_admin_token or not compare_digest(x_delir_admin_token, admin_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permesso amministrativo richiesto per questa operazione.",
        )

    return principal.model_copy(update={"is_admin": True})


async def authenticate_websocket(websocket: WebSocket) -> AuthPrincipal | None:
    try:
        tenant_id = normalize_tenant_id(websocket.query_params.get("tenant_id"))
        assert_allowed_tenant(tenant_id)
    except HTTPException:
        await websocket.close(code=1008)
        return None

    if not settings.delir_auth_enabled:
        principal = AuthPrincipal(user_id="local-dev", tenant_id=tenant_id, is_admin=True)
        set_current_tenant_id(tenant_id)
        return principal

    supplied_token = websocket.query_params.get("api_token")
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.casefold().startswith("bearer "):
        supplied_token = auth_header[7:].strip()

    expected_token = _configured_api_token()
    if not supplied_token or not compare_digest(supplied_token, expected_token):
        await websocket.close(code=1008)
        return None

    principal = AuthPrincipal(user_id="api-client", tenant_id=tenant_id, auth_mode="bearer")
    set_current_tenant_id(tenant_id)
    return principal

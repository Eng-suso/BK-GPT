from __future__ import annotations

import asyncio
import json
import re
from contextvars import ContextVar, Token
from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.settings import environment_is_open, settings


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


def _admin_without_token() -> bool:
    """Se, senza ``DELIR_ADMIN_TOKEN``, chi ha il token API e' anche amministratore.

    Solo su una macchina di sviluppo. Altrove il token API e' condiviso fra
    tutti i client: senza un token amministrativo distinto, cancellare un
    cliente o svuotare il workspace sarebbe alla portata di chiunque lo abbia.
    Fail closed: senza token le operazioni amministrative si rifiutano.
    """
    return environment_is_open()


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


SUPABASE_PROVIDER = "supabase"
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenziali API mancanti o non valide.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _authenticate_bearer(supplied_token: str | None) -> tuple[str | None, str]:
    """Chi prova di essere il portatore del token: `(user_id, auth_mode)`.

    Con il token condiviso l'identita' non esiste (`None`): il token prova solo
    di essere un client autorizzato. Con Supabase l'identita' e' il `sub` del
    token, e solo quello: un header non puo' cambiarla.

    Raises:
        HTTPException: 401 se il token non prova niente; 503 se Supabase non e'
            verificabile da troppo tempo o non e' autorizzato come destinazione.
    """
    if not supplied_token:
        raise _UNAUTHORIZED

    if settings.delir_auth_provider == SUPABASE_PROVIDER:
        from backend.auth.supabase_jwt import (
            IdentityProviderUnavailable,
            InvalidAccessToken,
            get_verifier,
        )
        from backend.llm.egress import EgressBlocked

        try:
            identity = get_verifier().verify(supplied_token)
        except InvalidAccessToken as exc:
            raise _UNAUTHORIZED from exc
        except (IdentityProviderUnavailable, EgressBlocked) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verifica dell'identita' non disponibile.",
            ) from exc
        return identity.subject, SUPABASE_PROVIDER

    if not compare_digest(supplied_token, _configured_api_token()):
        raise _UNAUTHORIZED
    return None, "bearer"


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

    subject, auth_mode = _authenticate_bearer(_token_from_credentials(credentials))

    principal = AuthPrincipal(
        user_id=subject or x_delir_user_id or "api-client",
        tenant_id=tenant_id,
        is_admin=not (settings.delir_admin_token or "").strip() and _admin_without_token(),
        auth_mode=auth_mode,
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
        if _admin_without_token():
            return principal.model_copy(update={"is_admin": True})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Operazione amministrativa non disponibile: DELIR_ADMIN_TOKEN non e' "
                "configurato in questo ambiente."
            ),
        )

    if not x_delir_admin_token or not compare_digest(x_delir_admin_token, admin_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permesso amministrativo richiesto per questa operazione.",
        )

    return principal.model_copy(update={"is_admin": True})


async def authenticate_websocket(websocket: WebSocket) -> AuthPrincipal | None:
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 4096:
            raise ValueError("oversized authentication message")
        credentials = json.loads(raw)
        if not isinstance(credentials, dict) or credentials.get("type") != "auth":
            raise ValueError("invalid authentication message")
        supplied_tenant = credentials.get("tenant_id")
        supplied_token = credentials.get("api_token")
        if (
            not isinstance(supplied_tenant, str)
            or not supplied_tenant.strip()
            or not isinstance(supplied_token, str)
        ):
            raise ValueError("invalid authentication fields")
        tenant_id = normalize_tenant_id(supplied_tenant)
        assert_allowed_tenant(tenant_id)
    except WebSocketDisconnect:
        return None
    except (HTTPException, ValueError, asyncio.TimeoutError):
        await websocket.close(code=1008)
        return None

    if not settings.delir_auth_enabled:
        principal = AuthPrincipal(user_id="local-dev", tenant_id=tenant_id, is_admin=True)
        set_current_tenant_id(tenant_id)
        return principal

    try:
        subject, auth_mode = _authenticate_bearer(supplied_token)
    except HTTPException as exc:
        # 1008: credenziali rifiutate; 1011: verifica non disponibile lato server.
        await websocket.close(code=1011 if exc.status_code >= 500 else 1008)
        return None

    principal = AuthPrincipal(
        user_id=subject or "api-client", tenant_id=tenant_id, auth_mode=auth_mode
    )
    set_current_tenant_id(tenant_id)
    return principal

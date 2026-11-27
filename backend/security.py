from __future__ import annotations

import asyncio
import json
import re
import uuid
from contextvars import ContextVar, Token
from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.settings import environment_is_open, settings


TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
DEFAULT_LOCAL_TENANT_ID = "local"
#: Lo spazio di lavoro di un account personale si chiama `acct-<sub>`. Il
#: prefisso e' riservato: nessun header puo' sceglierlo, lo assegna solo il
#: server dopo aver verificato il token della persona.
ACCOUNT_TENANT_PREFIX = "acct-"
_tenant_id: ContextVar[str | None] = ContextVar("delir_tenant_id", default=None)
# Il consulente della richiesta. Lo legge solo il registro dei consumi (tramite
# l'operazione): non e' un'autorizzazione, e niente decide accessi su questo.
_user_id: ContextVar[str | None] = ContextVar("delir_user_id", default=None)
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


def account_tenant_id(subject: str) -> str:
    """Lo spazio di lavoro dell'account con questo `sub`: uno per persona.

    Raises:
        ValueError: se `subject` non e' un UUID (il `sub` di Supabase lo e').
    """
    return f"{ACCOUNT_TENANT_PREFIX}{uuid.UUID(str(subject))}"


def is_account_tenant(tenant_id: str | None) -> bool:
    return bool(tenant_id) and str(tenant_id).startswith(ACCOUNT_TENANT_PREFIX)


def consultant_id_for_tenant(tenant_id: str | None) -> str:
    """Il consulente canonical (memoria, grafo, Mem0) di uno spazio di lavoro.

    Un account personale ha il suo: l'UUID della persona. Ogni altro spazio
    (sviluppo, token condiviso del pilota) resta sul consulente di default, come
    prima: la memoria gia' salvata li' non si perde.
    """
    if is_account_tenant(tenant_id):
        return str(uuid.UUID(str(tenant_id)[len(ACCOUNT_TENANT_PREFIX):]))
    return str(settings.default_consultant_id)


def tenant_id_for_consultant(consultant_id: str) -> str | None:
    """L'inverso, per i worker che partono dal consulente: `None` = quello di default."""
    if str(consultant_id) == str(settings.default_consultant_id):
        return None
    return account_tenant_id(consultant_id)


def get_current_consultant_id() -> str:
    """Il consulente della richiesta (o del lavoro in coda) corrente.

    Si ricava dallo spazio di lavoro del contesto, che la richiesta prende dal
    token verificato e il worker dalla riga di coda: e' l'unico modo previsto
    di sapere di chi e' la memoria su cui si sta lavorando.
    """
    return consultant_id_for_tenant(get_current_tenant_id())


def get_current_user_id() -> str | None:
    return _user_id.get()


def set_current_user_id(user_id: str | None) -> Token[str | None]:
    return _user_id.set(user_id)


def _bind_principal(principal: AuthPrincipal) -> None:
    """Il tenant e il consulente della richiesta, nel contesto corrente."""
    set_current_tenant_id(principal.tenant_id)
    set_current_user_id(principal.user_id)


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


def requested_tenant_id(value: str | None) -> str:
    """Lo spazio di lavoro chiesto dal client (header o messaggio WebSocket).

    Lo spazio di un account non si chiede: un client col token condiviso che
    scrivesse `acct-<qualcuno>` leggerebbe la memoria di quella persona.
    """
    tenant_id = normalize_tenant_id(value)
    if is_account_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant non autorizzato.")
    assert_allowed_tenant(tenant_id)
    return tenant_id


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


def _account_principal(subject: str) -> AuthPrincipal:
    """Una persona autenticata: il suo spazio di lavoro e' il suo account."""
    try:
        tenant_id = account_tenant_id(subject)
    except ValueError as exc:
        raise _UNAUTHORIZED from exc
    return AuthPrincipal(user_id=subject, tenant_id=tenant_id, auth_mode=SUPABASE_PROVIDER)


def _resolve_principal(
    credentials: HTTPAuthorizationCredentials | None,
    x_delir_tenant_id: str | None,
    x_delir_user_id: str | None,
) -> AuthPrincipal:
    if settings.delir_auth_enabled:
        subject, auth_mode = _authenticate_bearer(_token_from_credentials(credentials))
        if auth_mode == SUPABASE_PROVIDER and subject:
            # L'header del tenant non conta: chi sei decide anche dove lavori.
            return _account_principal(subject)

    tenant_id = requested_tenant_id(x_delir_tenant_id)

    if not settings.delir_auth_enabled:
        return AuthPrincipal(
            user_id=x_delir_user_id or "local-dev",
            tenant_id=tenant_id,
            is_admin=True,
            auth_mode="local",
        )

    return AuthPrincipal(
        user_id=x_delir_user_id or "api-client",
        tenant_id=tenant_id,
        is_admin=not (settings.delir_admin_token or "").strip() and _admin_without_token(),
        auth_mode=auth_mode,
    )


async def require_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_delir_tenant_id: str | None = Header(default=None),
    x_delir_user_id: str | None = Header(default=None),
) -> AuthPrincipal:
    """Chi chiama, verificato. Lega tenant e consulente al contesto della richiesta.

    E' `async` per una ragione precisa: una dipendenza sincrona gira in un thread
    del pool, con una **copia** del contesto, e quello che imposta li' non arriva
    alla rotta. Il consulente non arrivava al registro dei consumi proprio per
    questo. La verifica del token resta nel pool (puo' leggere le chiavi
    pubbliche dalla rete); il legame col contesto si fa qui, nel task della
    richiesta, da cui la rotta lo eredita.
    """
    principal = await run_in_threadpool(
        _resolve_principal, credentials, x_delir_tenant_id, x_delir_user_id
    )
    _bind_principal(principal)
    request.state.auth_principal = principal
    return principal


def owns_its_workspace(principal: AuthPrincipal) -> bool:
    """Una persona nel proprio account: lo spazio e' solo suo, quindi lo governa."""
    return principal.auth_mode == SUPABASE_PROVIDER and principal.tenant_id == _safe_account_tenant(
        principal.user_id
    )


def _safe_account_tenant(subject: str) -> str | None:
    try:
        return account_tenant_id(subject)
    except ValueError:
        return None


def require_platform_admin(
    principal: AuthPrincipal = Depends(require_principal),
    x_delir_admin_token: str | None = Header(default=None),
) -> AuthPrincipal:
    """Chi gestisce la piattaforma (per esempio i limiti di spesa di ogni persona).

    Non basta essere padroni del proprio account: serve la chiave
    `DELIR_ADMIN_TOKEN`, che sta fuori dal browser.
    """
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


def require_admin_principal(
    principal: AuthPrincipal = Depends(require_principal),
    x_delir_admin_token: str | None = Header(default=None),
) -> AuthPrincipal:
    """Le operazioni distruttive su uno spazio di lavoro.

    Nel proprio account una persona puo' cancellare le sue cose; in uno spazio
    condiviso (token del pilota) serve la chiave amministrativa.
    """
    if owns_its_workspace(principal):
        return principal.model_copy(update={"is_admin": True})
    return require_platform_admin(principal, x_delir_admin_token)


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
    except WebSocketDisconnect:
        return None
    except (HTTPException, ValueError, asyncio.TimeoutError):
        await websocket.close(code=1008)
        return None

    try:
        principal = await run_in_threadpool(_websocket_principal, supplied_tenant, supplied_token)
    except HTTPException as exc:
        # 1008: credenziali rifiutate; 1011: verifica non disponibile lato server.
        await websocket.close(code=1011 if exc.status_code >= 500 else 1008)
        return None

    _bind_principal(principal)
    return principal


def _websocket_principal(supplied_tenant: str, supplied_token: str) -> AuthPrincipal:
    """Come `_resolve_principal`, con il token nel primo messaggio invece che nell'header."""
    if settings.delir_auth_enabled:
        subject, auth_mode = _authenticate_bearer(supplied_token)
        if auth_mode == SUPABASE_PROVIDER and subject:
            return _account_principal(subject)
        return AuthPrincipal(
            user_id="api-client", tenant_id=requested_tenant_id(supplied_tenant), auth_mode=auth_mode
        )
    return AuthPrincipal(
        user_id="local-dev", tenant_id=requested_tenant_id(supplied_tenant), is_admin=True
    )

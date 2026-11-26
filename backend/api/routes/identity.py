"""Chi sta usando il prodotto, per quanto il backend lo sappia davvero.

La barra in alto mostrava un nome e un'organizzazione scritti nel codice
("Marco Bianchi", "Gruppo DeliR"): davanti a un cliente sono la prima cosa che
si legge, e dicono una cosa falsa.

Cio' che il backend sa oggi e' meno di una persona: lo spazio di lavoro
(`tenant`), con quale modalita' la richiesta e' stata autenticata e se ha
permessi amministrativi. L'identita' per persona - chi ha validato un modello,
chi ha risposto a una domanda del piano - arriva con l'autenticazione vera
(Supabase Auth, Track B): finche' non c'e', il prodotto lo dice invece di
inventare un nome.
"""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.security import AuthPrincipal, require_principal
from backend.settings import settings

router = APIRouter(prefix="/v1", tags=["identity"], dependencies=[Depends(require_principal)])


class CurrentIdentity(BaseModel):
    """Cio' che il backend puo' dire del chiamante, senza aggiungere nulla."""

    #: Lo spazio di lavoro a cui la richiesta e' associata.
    tenant_id: str
    #: `local` (nessuna autenticazione configurata), `bearer` (token condiviso) o
    #: `supabase` (access token di una persona).
    auth_mode: str
    #: Se l'autenticazione e' accesa in questo ambiente.
    auth_enabled: bool
    #: Se questo chiamante puo' fare operazioni distruttive.
    is_admin: bool
    #: L'id di chi chiama: con `supabase` e' l'id della persona in Supabase
    #: Auth, altrimenti il client.
    caller_id: str
    #: Se l'identita' per persona esiste: vero solo con `supabase`.
    has_user_identity: bool = False


@router.get("/auth/me")
def get_current_identity(
    principal: AuthPrincipal = Depends(require_principal),
) -> CurrentIdentity:
    """Lo spazio di lavoro e la modalita' di accesso della richiesta corrente."""
    return CurrentIdentity(
        tenant_id=principal.tenant_id,
        auth_mode=principal.auth_mode,
        auth_enabled=bool(settings.delir_auth_enabled),
        is_admin=principal.is_admin,
        caller_id=principal.user_id,
        # Solo un access token Supabase prova una persona; il token condiviso
        # prova un client, e allora l'unica cosa vera da mostrare e' lo spazio.
        has_user_identity=principal.auth_mode == "supabase",
    )


#: Pubblico per costruzione: serve al browser *prima* di avere credenziali.
public_router = APIRouter(prefix="/v1", tags=["identity"])


class AuthConfig(BaseModel):
    """Come il browser deve provare chi e': niente segreti, solo indirizzi pubblici."""

    #: `local` (autenticazione spenta), `token` (token condiviso del pilota) o
    #: `supabase` (login per persona).
    provider: Literal["local", "token", "supabase"]
    #: Con `supabase`: l'URL del progetto e la chiave *publishable*, pensata
    #: per stare nel browser. Altrimenti vuoti.
    supabase_url: str = ""
    supabase_publishable_key: str = ""


@public_router.get("/auth/config")
def get_auth_config() -> AuthConfig:
    """Letta a runtime e non incisa nel bundle: la stessa immagine va in ogni ambiente."""
    if not settings.delir_auth_enabled:
        return AuthConfig(provider="local")
    # Un valore diverso da questi non arriva qui: l'avvio lo rifiuta.
    provider = cast(Literal["token", "supabase"], settings.delir_auth_provider)
    if provider != "supabase":
        return AuthConfig(provider=provider)
    return AuthConfig(
        provider=provider,
        supabase_url=settings.supabase_url.rstrip("/"),
        supabase_publishable_key=settings.supabase_publishable_key,
    )

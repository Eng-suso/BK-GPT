"""Il contatore d'uso: cosa vede il consulente, cosa cambia l'amministratore."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.llm import budget
from backend.security import (
    SUPABASE_PROVIDER,
    AuthPrincipal,
    account_tenant_id,
    require_platform_admin,
    require_principal,
)
from backend.settings import settings

router = APIRouter(prefix="/v1/usage", tags=["usage"], dependencies=[Depends(require_principal)])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _window(window: budget.Window) -> dict:
    """Una finestra per il pannello: quota e orari. Niente dollari al consulente."""
    return {
        "used_share": round(window.used_share, 4),
        "limited": window.limit_usd is not None,
        "exhausted": window.exhausted,
        "started_at": _iso(window.started_at),
        "resets_at": _iso(window.resets_at),
    }


def _audio(window: budget.AudioWindow) -> dict:
    """L'audio in secondi: il pannello lo mostra in ore e minuti."""
    return {
        "used_seconds": window.used_seconds,
        "limit_seconds": window.limit_seconds,
        "exhausted": window.exhausted,
        "resets_at": _iso(window.resets_at),
    }


def _status(current: budget.UsageStatus) -> dict:
    blocking = current.blocking
    forecast = current.forecast
    return {
        "enabled": current.enabled,
        # La durata della sessione e' una configurazione: il pannello la dice
        # invece di scriverla a mano.
        "session_hours": settings.usage_session_hours,
        "session": _window(current.session),
        "week": _window(current.week),
        "trial": {**_window(current.trial), "over": current.trial_over},
        "blocking": blocking.name if blocking else None,
        "audio": {
            "week": _audio(current.audio_week),
            "trial": _audio(current.audio_trial),
            "blocking": current.audio_blocking.name if current.audio_blocking else None,
        },
        "forecast": (
            {
                "window": forecast.window,
                "exhausts_at": _iso(forecast.exhausts_at),
                "resets_at": _iso(forecast.resets_at),
            }
            if forecast
            else None
        ),
    }


@router.get("/me")
def my_usage(principal: AuthPrincipal = Depends(require_principal)) -> dict:
    """Quanto ha usato il consulente e quando si ripristina.

    Con i limiti spenti non si legge niente: il pannello non compare, e la
    barra lo chiede a ogni apertura dell'app.
    """
    if not settings.usage_limits_enabled:
        return {"enabled": False, "session_hours": settings.usage_session_hours}
    return _status(budget.status(principal.user_id))


class PlanUpdate(BaseModel):
    """Le soglie in dollari stimati. Un campo omesso resta com'e'; 0 = nessun tetto."""

    session_budget_usd: Decimal | None = Field(default=None, ge=0)
    week_budget_usd: Decimal | None = Field(default=None, ge=0)
    trial_budget_usd: Decimal | None = Field(default=None, ge=0)
    trial_ends_at: datetime | None = None
    week_audio_hours: Decimal | None = Field(default=None, ge=0)
    trial_audio_hours: Decimal | None = Field(default=None, ge=0)
    reset_session: bool = False


def _admin_view(current: budget.UsageStatus) -> dict:
    """Per l'amministratore anche gli importi: sono loro a decidere il budget."""
    view = _status(current)
    for window in current.windows:
        view[window.name] |= {
            "used_usd": str(window.used_usd.quantize(Decimal("0.0001"))),
            "limit_usd": str(window.limit_usd) if window.limit_usd is not None else None,
        }
    return {"user_id": current.user_id, **view}


def _plan_owner(user_id: str, admin: AuthPrincipal) -> tuple[str, str]:
    """Di chi e' il piano, e in quale spazio vive: `(user_id, tenant_id)`.

    Con gli account personali ognuno ha il suo spazio, quindi il piano di una
    persona sta nel suo account e non in quello di chi lo amministra. L'id si
    normalizza come lo scrive Supabase (minuscolo, con i trattini): un UUID
    scritto diverso creerebbe un piano che nessuna richiesta legge. Con il
    token condiviso resta lo spazio della richiesta.

    Raises:
        HTTPException: 422 se, con gli account personali, `user_id` non e' l'id
            (UUID) di una persona.
    """
    if admin.auth_mode != SUPABASE_PROVIDER:
        return user_id, admin.tenant_id
    try:
        normalized = str(uuid.UUID(user_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="user_id deve essere l'id (UUID) dell'account."
        ) from exc
    return normalized, account_tenant_id(normalized)


@router.get("/plans/{user_id}")
def get_plan(user_id: str, admin: AuthPrincipal = Depends(require_platform_admin)) -> dict:
    # Solo lettura: guardare il piano di un id non crea niente.
    owner, tenant_id = _plan_owner(user_id, admin)
    return _admin_view(budget.status(owner, tenant_id=tenant_id))


@router.put("/plans/{user_id}")
def put_plan(
    user_id: str,
    update: PlanUpdate,
    admin: AuthPrincipal = Depends(require_platform_admin),
) -> dict:
    owner, tenant_id = _plan_owner(user_id, admin)
    return _admin_view(budget.update_plan(owner, tenant_id=tenant_id, **update.model_dump()))

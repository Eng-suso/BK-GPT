"""Il limite d'uso della prova: quanto ha usato un consulente e quanto gli resta.

Tre finestre, come in Claude e in Codex:

- **sessione**: parte dal primo uso e dura `usage_session_hours`. Finita, la
  successiva parte alla prossima richiesta, non a un orario fisso;
- **settimana**: blocchi di sette giorni agganciati all'inizio della prova;
- **prova**: il tetto assoluto, fino alla fine della prova.

La spesa non si copia da nessuna parte: si legge dal registro dei consumi
(`workspace_llm_usage`), che resta l'unica fonte. Qui ci sono solo le soglie e
l'inizio della sessione in corso (`workspace_usage_plans`).

Due regole di comportamento, che contano piu' del codice:

- **un lavoro iniziato finisce.** Il controllo si fa all'inizio di un turno di
  chat o di un'azione chiesta dal consulente, non a meta': un turno che si ferma
  a meta' butta la spesa gia' fatta e lascia il consulente senza risposta;
- **il lavoro in background non si ferma.** L'estrazione di un file gia' caricato,
  la proiezione della memoria, la ricostruzione del piano sono lavoro gia'
  accettato: si conta, non si blocca. Si blocca la prossima richiesta.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.llm.operation import Operation, OperationKind
from backend.settings import settings

_MILLION = Decimal(1_000_000)
_WEEK = timedelta(days=7)
# Una previsione su pochi minuti di uso e' rumore: un turno solo sembrerebbe un
# ritmo che esaurisce tutto in un'ora.
_FORECAST_MIN_ELAPSED = timedelta(minutes=15)
_FORECAST_MIN_SHARE = 0.25
# Il controllo nel gateway gira a ogni chiamata: lo stato si tiene per pochi
# secondi invece di rileggere il registro ogni volta.
_CACHE_SECONDS = 10.0

#: Le operazioni che un consulente chiede da un'azione diretta, oltre al turno di
#: chat (che si controlla all'inizio, in `agent_runtime`). Tutto il resto e'
#: lavoro in background gia' accettato.
GATED_KINDS = frozenset(
    {
        OperationKind.BPMN_DRAFT,
        OperationKind.CLAIM_MATCHING,
        OperationKind.SIMULATION_WHAT_IF,
        OperationKind.SIMULATION_NARRATIVE,
        OperationKind.TRANSCRIPTION,
    }
)


@dataclass(frozen=True, slots=True)
class Window:
    """Una finestra d'uso.

    Attributes:
        name: `session`, `week` o `trial`.
        used_usd: La spesa stimata nella finestra.
        limit_usd: La soglia, o `None` se la finestra non ha tetto.
        started_at: Quando e' cominciata, o `None` se non e' aperta (una sessione
            che partira' alla prossima richiesta).
        resets_at: Quando si azzera (o, per la prova, quando finisce).
    """

    name: str
    used_usd: Decimal
    limit_usd: Decimal | None
    started_at: datetime | None
    resets_at: datetime | None

    @property
    def used_share(self) -> float:
        if not self.limit_usd:
            return 0.0
        return min(1.0, float(self.used_usd / self.limit_usd))

    @property
    def exhausted(self) -> bool:
        return self.limit_usd is not None and self.used_usd >= self.limit_usd


@dataclass(frozen=True, slots=True)
class Forecast:
    """Il ritmo attuale esaurisce una finestra prima che si azzeri."""

    window: str
    exhausts_at: datetime
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class UsageStatus:
    """Lo stato d'uso di un consulente, cosi' come lo vede il pannello."""

    enabled: bool
    user_id: str
    session: Window
    week: Window
    trial: Window
    trial_over: bool = False
    forecast: Forecast | None = None

    @property
    def windows(self) -> tuple[Window, ...]:
        return (self.session, self.week, self.trial)

    @property
    def blocking(self) -> Window | None:
        """La finestra che ferma le richieste nuove, se ce n'e' una."""
        if not self.enabled:
            return None
        if self.trial_over:
            return self.trial
        return next((w for w in (self.session, self.week, self.trial) if w.exhausted), None)


class UsageLimitReached(Exception):
    """Una richiesta nuova oltre il limite. Il messaggio e' per il consulente."""

    def __init__(self, status: UsageStatus) -> None:
        self.status = status
        window = status.blocking
        name = window.name if window else "session"
        super().__init__(_MESSAGES["trial_over" if status.trial_over else name])


# Linguaggio del consulente, non del fornitore: niente token, niente dollari.
# L'ora del ripristino la mostra il pannello, nel fuso del consulente.
_MESSAGES = {
    "session": (
        "Hai usato tutta la sessione di lavoro. Quello che hai fatto e' salvato: "
        "puoi riprendere quando la sessione si ripristina (vedi Utilizzo, in alto)."
    ),
    "week": (
        "Hai raggiunto il limite settimanale. Quello che hai fatto e' salvato: "
        "riprendi quando la settimana si rinnova (vedi Utilizzo, in alto)."
    ),
    "trial": (
        "Hai usato tutto il credito della prova. Quello che hai fatto resta "
        "consultabile; per continuare a lavorare contatta il team DeliR."
    ),
    "trial_over": (
        "La prova e' terminata. Quello che hai fatto resta consultabile; per "
        "continuare a lavorare contatta il team DeliR."
    ),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _money(value: str | None, default: float) -> Decimal:
    return Decimal(value) if value is not None else Decimal(str(default))


def _spent_since(user_id: str, since: datetime, until: datetime) -> Decimal:
    """La spesa stimata di un consulente in una finestra.

    Le righe senza prezzo (modello non nel listino) si contano al prezzo di
    ripiego, pessimista: un costo sconosciuto non deve far sforare il budget.
    """
    from backend.llm import ledger

    total = ledger.totale(since=since.isoformat(), until=until.isoformat(), user_id=user_id)
    unpriced_rate = Decimal(str(settings.usage_unpriced_usd_per_million_tokens))
    return total.costo_noto + Decimal(total.token_senza_prezzo) * unpriced_rate / _MILLION


def _plan(user_id: str, now: datetime, *, open_session: bool):
    """Il piano del consulente, creato al primo uso; apre la sessione se serve."""
    from backend.security import get_current_tenant_id
    from backend.workspace_storage import WorkspaceUsagePlan, workspace_connection

    session_length = timedelta(hours=settings.usage_session_hours)
    with workspace_connection() as session:
        plan = session.get(WorkspaceUsagePlan, user_id, with_for_update=open_session)
        if plan is None:
            plan = WorkspaceUsagePlan(
                user_id=user_id,
                tenant_id=get_current_tenant_id(),
                trial_started_at=now.isoformat(),
                updated_at=now.isoformat(),
            )
            session.add(plan)
        started = _parse(plan.session_started_at)
        if open_session and (started is None or now >= started + session_length):
            plan.session_started_at = now.isoformat()
            plan.updated_at = now.isoformat()
        session.flush()
        session.expunge(plan)
    return plan


def _forecast(windows: tuple[Window, ...], now: datetime) -> Forecast | None:
    """La finestra che, al ritmo attuale, finisce prima di azzerarsi; la piu' vicina."""
    best: Forecast | None = None
    for window in windows:
        if (
            window.limit_usd is None
            or window.started_at is None
            or window.resets_at is None
            or window.exhausted
            or window.used_share < _FORECAST_MIN_SHARE
        ):
            continue
        elapsed = now - window.started_at
        if elapsed < _FORECAST_MIN_ELAPSED or window.used_usd <= 0:
            continue
        rate_per_second = window.used_usd / Decimal(elapsed.total_seconds())
        remaining = window.limit_usd - window.used_usd
        exhausts_at = now + timedelta(seconds=float(remaining / rate_per_second))
        if exhausts_at < window.resets_at and (best is None or exhausts_at < best.exhausts_at):
            best = Forecast(window=window.name, exhausts_at=exhausts_at, resets_at=window.resets_at)
    return best


def status(user_id: str, *, now: datetime | None = None, open_session: bool = False) -> UsageStatus:
    """Lo stato d'uso di un consulente.

    Args:
        user_id: Il consulente.
        now: L'istante di riferimento (i test lo fissano).
        open_session: Apre una sessione nuova se non ce n'e' una in corso. Lo fa
            solo chi sta per spendere (`enforce`, l'inizio di un turno): guardare
            il pannello non deve far partire il cronometro.
    """
    now = now or _now()
    plan = _plan(user_id, now, open_session=open_session)

    session_length = timedelta(hours=settings.usage_session_hours)
    session_start = _parse(plan.session_started_at)
    if session_start is not None and now >= session_start + session_length:
        session_start = None
    session = Window(
        name="session",
        used_usd=_spent_since(user_id, session_start, now) if session_start else Decimal(0),
        limit_usd=_money(plan.session_budget_usd, settings.usage_session_budget_usd),
        started_at=session_start,
        resets_at=session_start + session_length if session_start else None,
    )

    trial_start = _parse(plan.trial_started_at) or now
    trial_end = _parse(plan.trial_ends_at) or trial_start + timedelta(days=settings.usage_trial_days)
    weeks_elapsed = max(0, int((now - trial_start) / _WEEK))
    week_start = trial_start + weeks_elapsed * _WEEK
    week = Window(
        name="week",
        used_usd=_spent_since(user_id, week_start, now),
        limit_usd=_money(plan.week_budget_usd, settings.usage_week_budget_usd),
        started_at=week_start,
        resets_at=week_start + _WEEK,
    )

    trial_limit = _money(plan.trial_budget_usd, settings.usage_trial_budget_usd)
    trial = Window(
        name="trial",
        used_usd=_spent_since(user_id, trial_start, now),
        limit_usd=trial_limit if trial_limit > 0 else None,
        started_at=trial_start,
        resets_at=trial_end,
    )

    windows = (session, week, trial)
    return UsageStatus(
        enabled=settings.usage_limits_enabled,
        user_id=user_id,
        session=session,
        week=week,
        trial=trial,
        trial_over=now >= trial_end,
        forecast=_forecast(windows, now),
    )


_cache: dict[str, tuple[float, UsageStatus]] = {}


def check(user_id: str | None) -> None:
    """Ferma una richiesta nuova oltre il limite. Apre la sessione se non c'e'.

    Raises:
        UsageLimitReached: Se una finestra e' esaurita o la prova e' finita.
    """
    if not settings.usage_limits_enabled or not user_id:
        return
    cached = _cache.get(user_id)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_SECONDS:
        current = cached[1]
    else:
        current = status(user_id, open_session=True)
        _cache[user_id] = (time.monotonic(), current)
    if current.blocking is not None:
        raise UsageLimitReached(current)


def enforce(operation: Operation) -> None:
    """Il controllo del gateway: solo per le azioni dirette del consulente.

    Un'operazione figlia (un «Genera BPMN» chiesto da un turno di chat) fa parte
    di un lavoro gia' accettato, e il lavoro in background non si ferma: entrambi
    passano. Vedi la docstring del modulo.
    """
    if operation.parent_id is not None or operation.kind not in GATED_KINDS:
        return
    check(operation.user_id)


def reset_cache() -> None:
    """Per i test, e per l'amministratore che cambia un piano."""
    _cache.clear()


def update_plan(
    user_id: str,
    *,
    session_budget_usd: Decimal | None = None,
    week_budget_usd: Decimal | None = None,
    trial_budget_usd: Decimal | None = None,
    trial_ends_at: datetime | None = None,
    reset_session: bool = False,
) -> UsageStatus:
    """Cambia il piano di un consulente (amministrazione). I campi omessi restano.

    `reset_session` chiude la sessione in corso: la prossima richiesta ne apre
    una nuova, a contatore pieno. E' il «ripristino» che l'amministratore puo'
    concedere a mano.
    """
    from backend.workspace_storage import WorkspaceUsagePlan, workspace_connection

    now = _now()
    _plan(user_id, now, open_session=False)
    with workspace_connection() as session:
        plan = session.get(WorkspaceUsagePlan, user_id, with_for_update=True)
        assert plan is not None  # creato qui sopra
        if session_budget_usd is not None:
            plan.session_budget_usd = str(session_budget_usd)
        if week_budget_usd is not None:
            plan.week_budget_usd = str(week_budget_usd)
        if trial_budget_usd is not None:
            plan.trial_budget_usd = str(trial_budget_usd)
        if trial_ends_at is not None:
            plan.trial_ends_at = trial_ends_at.astimezone(UTC).isoformat()
        if reset_session:
            plan.session_started_at = None
        plan.updated_at = now.isoformat()
    _cache.pop(user_id, None)
    return status(user_id, now=now)

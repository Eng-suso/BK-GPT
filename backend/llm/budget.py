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

- **un lavoro iniziato finisce.** Il controllo si fa una volta, al confine:
  all'inizio di un turno di chat e, per le azioni dirette del consulente, nella
  dipendenza della rotta (`require_usage_available`). Mai dentro il gateway,
  a meta' di un lavoro: fermarlo li' butterebbe la spesa gia' fatta e
  lascerebbe un risultato a meta';
- **il lavoro in background non si ferma.** L'estrazione di un file gia' caricato,
  la proiezione della memoria, la ricostruzione del piano sono lavoro gia'
  accettato: si conta, non si blocca. Si blocca la prossima richiesta.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import Depends

from backend.security import AuthPrincipal, require_principal

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
class AudioWindow:
    """Una finestra dell'audio: secondi usati e tetto in secondi.

    L'audio ha un tetto suo, in ore, separato dai dollari dei modelli: costa piu'
    di tutto il resto, e' prevedibile, e il consulente lo legge come ore di
    registrazione. Quando e' esaurito si fermano solo le registrazioni e le
    trascrizioni: la chat e il resto continuano.
    """

    name: str
    used_seconds: int
    limit_seconds: int | None
    resets_at: datetime | None

    @property
    def used_share(self) -> float:
        if not self.limit_seconds:
            return 0.0
        return min(1.0, self.used_seconds / self.limit_seconds)

    @property
    def exhausted(self) -> bool:
        return self.limit_seconds is not None and self.used_seconds >= self.limit_seconds


@dataclass(frozen=True, slots=True)
class UsageStatus:
    """Lo stato d'uso di un consulente, cosi' come lo vede il pannello."""

    enabled: bool
    user_id: str
    session: Window
    week: Window
    trial: Window
    audio_week: AudioWindow
    audio_trial: AudioWindow
    trial_over: bool = False
    forecast: Forecast | None = None

    @property
    def windows(self) -> tuple[Window, ...]:
        return (self.session, self.week, self.trial)

    @property
    def audio_blocking(self) -> AudioWindow | None:
        """La finestra dell'audio che ferma registrazioni e trascrizioni nuove."""
        if not self.enabled:
            return None
        if self.trial_over:
            return self.audio_trial
        return next((w for w in (self.audio_trial, self.audio_week) if w.exhausted), None)

    @property
    def blocking(self) -> Window | None:
        """La finestra che ferma le richieste nuove, se ce n'e' una.

        Fra piu' finestre esaurite vince quella che si ripristina **per ultima**:
        e' l'unica che dice davvero quando si potra' riprendere. Dire l'ora della
        sessione con la settimana gia' esaurita sarebbe una promessa falsa.
        """
        if not self.enabled:
            return None
        if self.trial_over:
            return self.trial
        exhausted = [w for w in self.windows if w.exhausted]
        if not exhausted:
            return None
        far_future = datetime.max.replace(tzinfo=UTC)
        return max(exhausted, key=lambda w: w.resets_at or far_future)


class UsageLimitReached(Exception):
    """Una richiesta nuova oltre il limite. Il messaggio e' per il consulente.

    Attributes:
        window: La finestra che ferma (`session`, `week`, `trial`, `trial_over`).
    """

    def __init__(self, message: str, window: str) -> None:
        super().__init__(message)
        self.window = window

    @classmethod
    def from_status(cls, status: UsageStatus) -> UsageLimitReached:
        blocking = status.blocking
        assert blocking is not None, "from_status si chiama solo con una finestra che blocca"
        name = "trial_over" if status.trial_over else blocking.name
        return cls(_MESSAGES[name], name)


def _audio_limit_reached(status: UsageStatus) -> UsageLimitReached:
    window = status.audio_blocking
    assert window is not None, "si chiama solo con una finestra dell'audio che blocca"
    name = "trial_over" if status.trial_over else f"audio_{window.name}"
    return UsageLimitReached(_MESSAGES[name], name)


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
    "audio_week": (
        "Hai usato tutte le ore di registrazione di questa settimana. La chat e il "
        "resto continuano; le registrazioni riprendono quando la settimana si "
        "rinnova (vedi Utilizzo, in alto)."
    ),
    "audio_trial": (
        "Hai usato tutte le ore di registrazione della prova. La chat e il resto "
        "continuano; per registrare ancora contatta il team DeliR."
    ),
    "trial_over": (
        "La prova e' terminata. Quello che hai fatto resta consultabile; per "
        "continuare a lavorare contatta il team DeliR."
    ),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    """Un istante senza fuso si legge come UTC, sempre: mai come l'ora del server."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse(value: str | None) -> datetime | None:
    return _utc(datetime.fromisoformat(value)) if value else None


def _limit(value: str | None, default: float) -> Decimal | None:
    """La soglia di una finestra. Zero vuol dire «nessun tetto», per tutte e tre."""
    amount = Decimal(value) if value is not None else Decimal(str(default))
    return amount if amount > 0 else None


def _session_length() -> timedelta:
    return timedelta(hours=settings.usage_session_hours)


def _live_session_start(plan, now: datetime) -> datetime | None:
    """L'inizio della sessione in corso, o `None` se non ce n'e' una (mai aperta o scaduta)."""
    started = _parse(plan.session_started_at)
    return started if started is not None and now < started + _session_length() else None


def _spent(
    tenant_id: str, user_id: str, starts: dict[str, datetime], now: datetime
) -> tuple[dict[str, Decimal], dict[str, int]]:
    """Spesa dei modelli in dollari e audio in secondi, con una sola lettura del registro.

    Le righe dei modelli senza prezzo si contano al prezzo di ripiego,
    pessimista: un costo sconosciuto non deve far sforare il budget. L'audio non
    entra nei dollari: ha il suo tetto in ore.
    """
    from backend.llm import ledger

    models, audio = ledger.per_finestre(
        {name: start.isoformat() for name, start in starts.items()},
        fine=now.isoformat(),
        tenant_id=tenant_id,
        user_id=user_id,
    )
    unpriced_rate = Decimal(str(settings.usage_unpriced_usd_per_million_tokens))
    usd = {
        name: total.costo_noto + Decimal(total.token_senza_prezzo) * unpriced_rate / _MILLION
        for name, total in models.items()
    }
    return usd, {name: total.secondi_audio for name, total in audio.items()}


def _hours_limit(value: str | None, default: float) -> int | None:
    """Il tetto dell'audio in secondi, da ore. Zero vuol dire «nessun tetto»."""
    hours = Decimal(value) if value is not None else Decimal(str(default))
    seconds = int(hours * 3600)
    # Un tetto sotto il secondo non e' un tetto: vale "nessun tetto", come lo zero.
    return seconds if seconds > 0 else None


def _new_plan_values(tenant_id: str, user_id: str, now: datetime) -> dict:
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "trial_started_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _locked_plan(session, tenant_id: str, user_id: str, now: datetime):
    """Il piano, creato se manca, bloccato per la transazione in corso.

    `INSERT ... ON CONFLICT DO NOTHING`: due prime richieste simultanee di un
    consulente nuovo non si scontrano sulla chiave.
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from backend.workspace_storage import WorkspaceUsagePlan

    session.execute(
        insert(WorkspaceUsagePlan)
        .values(**_new_plan_values(tenant_id, user_id, now))
        .on_conflict_do_nothing(index_elements=["tenant_id", "user_id"])
    )
    return session.scalars(
        select(WorkspaceUsagePlan)
        .where(WorkspaceUsagePlan.tenant_id == tenant_id, WorkspaceUsagePlan.user_id == user_id)
        .with_for_update()
    ).one()


def _plan(tenant_id: str, user_id: str, now: datetime, *, open_session: bool):
    """Il piano del consulente.

    Si legge prima, senza scrivere niente. Si scrive soltanto quando serve: con
    `open_session` e senza una sessione in corso, il piano si crea (se manca) e
    la sessione si apre. Guardare il pannello - che lo chiede ogni minuto - non
    crea niente e non fa partire la prova: sarebbe gia' scaduta per tutti il
    giorno in cui i limiti si accendono. Un consulente senza piano riceve un
    piano provvisorio, che non si salva.
    """
    from sqlalchemy import select

    from backend.workspace_storage import WorkspaceUsagePlan, workspace_connection

    with workspace_connection() as session:
        plan = session.scalars(
            select(WorkspaceUsagePlan).where(
                WorkspaceUsagePlan.tenant_id == tenant_id, WorkspaceUsagePlan.user_id == user_id
            )
        ).one_or_none()
        if open_session and (plan is None or _live_session_start(plan, now) is None):
            plan = _locked_plan(session, tenant_id, user_id, now)
            if _live_session_start(plan, now) is None:
                plan.session_started_at = now.isoformat()
                plan.updated_at = now.isoformat()
            session.flush()
        if plan is None:
            return WorkspaceUsagePlan(**_new_plan_values(tenant_id, user_id, now))
        session.expunge(plan)
    return plan


def _forecast(windows: tuple[Window, ...], now: datetime) -> Forecast | None:
    """La finestra che, al ritmo attuale, finisce prima di azzerarsi; la piu' vicina."""
    best: Forecast | None = None
    for window in windows:
        # Senza tetto la quota e' 0, e sotto la soglia minima non si prevede niente.
        if window.exhausted or window.used_share < _FORECAST_MIN_SHARE:
            continue
        if window.started_at is None or window.resets_at is None or window.limit_usd is None:
            continue
        elapsed = now - window.started_at
        if elapsed < _FORECAST_MIN_ELAPSED:
            continue
        rate_per_second = window.used_usd / Decimal(elapsed.total_seconds())
        remaining = window.limit_usd - window.used_usd
        exhausts_at = now + timedelta(seconds=float(remaining / rate_per_second))
        if exhausts_at < window.resets_at and (best is None or exhausts_at < best.exhausts_at):
            best = Forecast(window=window.name, exhausts_at=exhausts_at, resets_at=window.resets_at)
    return best


def _tenant(tenant_id: str | None) -> str:
    from backend.security import get_current_tenant_id

    return tenant_id or get_current_tenant_id()


def _status_of(plan, user_id: str, now: datetime) -> UsageStatus:
    """Le tre finestre di un piano, con la spesa letta una volta sola."""
    session_start = _live_session_start(plan, now)
    trial_start = _parse(plan.trial_started_at) or now
    trial_end = _parse(plan.trial_ends_at) or trial_start + timedelta(days=settings.usage_trial_days)
    week_start = trial_start + max(0, int((now - trial_start) / _WEEK)) * _WEEK

    starts = {"week": week_start, "trial": trial_start}
    if session_start is not None:
        starts["session"] = session_start
    spent, audio_seconds = _spent(plan.tenant_id, user_id, starts, now)

    session = Window(
        name="session",
        used_usd=spent.get("session", Decimal(0)),
        limit_usd=_limit(plan.session_budget_usd, settings.usage_session_budget_usd),
        started_at=session_start,
        resets_at=session_start + _session_length() if session_start else None,
    )
    week = Window(
        name="week",
        used_usd=spent["week"],
        limit_usd=_limit(plan.week_budget_usd, settings.usage_week_budget_usd),
        started_at=week_start,
        resets_at=week_start + _WEEK,
    )
    trial = Window(
        name="trial",
        used_usd=spent["trial"],
        limit_usd=_limit(plan.trial_budget_usd, settings.usage_trial_budget_usd),
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
        audio_week=AudioWindow(
            name="week",
            used_seconds=audio_seconds["week"],
            limit_seconds=_hours_limit(plan.week_audio_hours, settings.usage_week_audio_hours),
            resets_at=week_start + _WEEK,
        ),
        audio_trial=AudioWindow(
            name="trial",
            used_seconds=audio_seconds["trial"],
            limit_seconds=_hours_limit(plan.trial_audio_hours, settings.usage_trial_audio_hours),
            resets_at=trial_end,
        ),
        trial_over=now >= trial_end,
        forecast=_forecast(windows, now),
    )


def status(
    user_id: str,
    *,
    tenant_id: str | None = None,
    now: datetime | None = None,
    open_session: bool = False,
) -> UsageStatus:
    """Lo stato d'uso di un consulente.

    Args:
        user_id: Il consulente.
        tenant_id: Il suo tenant; omesso, quello della richiesta. Piani e spesa
            sono per tenant: lo stesso id in due tenant sono due persone.
        now: L'istante di riferimento (i test lo fissano).
        open_session: Apre una sessione (creando il piano, se manca) quando non
            ce n'e' una in corso. Solo chi sta per spendere: vedi `_plan`.
    """
    now = now or _now()
    plan = _plan(_tenant(tenant_id), user_id, now, open_session=open_session)
    return _status_of(plan, user_id, now)


_cache: dict[tuple[str, str], tuple[float, UsageStatus]] = {}


def _current(user_id: str, tenant_id: str | None, *, open_session: bool) -> UsageStatus:
    """Lo stato per un controllo, tenuto per pochi secondi per processo.

    Con `open_session` apre la sessione dei modelli se non c'e': lo fa solo chi
    sta per spendere sui modelli. Una registrazione no: l'audio ha il suo tetto,
    e non deve far partire il cronometro della chat.
    """
    tenant = _tenant(tenant_id)
    now_mono = time.monotonic()
    cached = _cache.get((tenant, user_id))
    # Uno stato letto senza aprire la sessione non basta a chi deve aprirla.
    if cached is not None and now_mono - cached[0] < _CACHE_SECONDS and (
        not open_session or cached[1].session.started_at is not None
    ):
        return cached[1]
    current = status(user_id, tenant_id=tenant, open_session=open_session)
    # Le voci scadute si buttano qui: il dizionario non cresce per sempre.
    for key in [k for k, (at, _) in _cache.items() if now_mono - at >= _CACHE_SECONDS]:
        del _cache[key]
    _cache[(tenant, user_id)] = (now_mono, current)
    return current


def check(user_id: str | None, *, tenant_id: str | None = None) -> None:
    """Ferma una richiesta nuova ai modelli oltre il limite.

    Raises:
        UsageLimitReached: Se una finestra dei modelli e' esaurita o la prova e' finita.
    """
    if not settings.usage_limits_enabled or not user_id:
        return
    current = _current(user_id, tenant_id, open_session=True)
    if current.blocking is not None:
        raise UsageLimitReached.from_status(current)


def check_audio(user_id: str | None, *, tenant_id: str | None = None) -> None:
    """Ferma una registrazione o una trascrizione nuova oltre il tetto dell'audio.

    Raises:
        UsageLimitReached: Se le ore della settimana o della prova sono finite,
            o la prova e' terminata.
    """
    if not settings.usage_limits_enabled or not user_id:
        return
    current = _current(user_id, tenant_id, open_session=False)
    if current.audio_blocking is not None:
        raise _audio_limit_reached(current)


def remaining_audio_seconds(user_id: str | None, *, tenant_id: str | None = None) -> int | None:
    """Quanti secondi di audio restano prima del tetto, o `None` se non c'e' tetto.

    Serve alla registrazione dal vivo, che si ferma dopo questo (piu' un
    margine): il controllo all'apertura da solo lascerebbe registrare per ore
    con un minuto di budget.
    """
    if not settings.usage_limits_enabled or not user_id:
        return None
    current = _current(user_id, tenant_id, open_session=False)
    left = [w.limit_seconds - w.used_seconds for w in (current.audio_week, current.audio_trial) if w.limit_seconds]
    return max(0, min(left)) if left else None


#: Quanto dopo la fine di una registrazione dal vivo il file della stessa
#: intervista arriva ancora come "seconda passata" (trascrizione con i nomi).
_AFTER_LIVE_WINDOW = timedelta(minutes=15)


def follows_live_recording(user_id: str | None, *, tenant_id: str | None = None, now: datetime | None = None) -> bool:
    """Se un file audio e' la seconda passata di una registrazione dal vivo appena finita.

    Il browser registra dal vivo e, all'arresto, manda lo stesso audio per la
    trascrizione con i nomi di chi parla. E' lo stesso audio: contarlo due volte
    raddoppierebbe le ore, e rifiutarlo lascerebbe l'intervista senza nomi. Si
    riconosce dal registro, non da un'etichetta del client: una riga
    `live_transcription` dello stesso consulente finita da poco.
    """
    if not user_id:
        return False
    from sqlalchemy import select

    from backend.llm.tasks import LlmTask
    from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

    now = now or _now()
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceLlmUsage.created_at, WorkspaceLlmUsage.audio_seconds).where(
                WorkspaceLlmUsage.tenant_id == _tenant(tenant_id),
                WorkspaceLlmUsage.user_id == user_id,
                WorkspaceLlmUsage.task == LlmTask.LIVE_TRANSCRIPTION.value,
                WorkspaceLlmUsage.created_at >= (now - timedelta(days=1)).isoformat(),
            )
        ).all()
    # La riga nasce all'apertura: la registrazione e' finita dopo i suoi secondi.
    ends = (
        started + timedelta(seconds=row.audio_seconds or 0)
        for row in rows
        if (started := _parse(row.created_at)) is not None
    )
    return any(end + _AFTER_LIVE_WINDOW >= now for end in ends)


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
    week_audio_hours: Decimal | None = None,
    trial_audio_hours: Decimal | None = None,
    reset_session: bool = False,
) -> UsageStatus:
    """Cambia il piano di un consulente (amministrazione). I campi omessi restano.

    Zero su una soglia vuol dire «nessun tetto». `reset_session` chiude la
    sessione in corso: la prossima richiesta ne apre una nuova, a contatore
    pieno. E' il «ripristino» che l'amministratore puo' concedere a mano.
    Una transazione sola: creare, bloccare e cambiare il piano.
    """
    from backend.workspace_storage import workspace_connection

    now = _now()
    tenant = _tenant(None)
    with workspace_connection() as session:
        plan = _locked_plan(session, tenant, user_id, now)
        if session_budget_usd is not None:
            plan.session_budget_usd = str(session_budget_usd)
        if week_budget_usd is not None:
            plan.week_budget_usd = str(week_budget_usd)
        if trial_budget_usd is not None:
            plan.trial_budget_usd = str(trial_budget_usd)
        if trial_ends_at is not None:
            plan.trial_ends_at = _utc(trial_ends_at).astimezone(UTC).isoformat()
        if week_audio_hours is not None:
            plan.week_audio_hours = str(week_audio_hours)
        if trial_audio_hours is not None:
            plan.trial_audio_hours = str(trial_audio_hours)
        if reset_session:
            plan.session_started_at = None
        plan.updated_at = now.isoformat()
        session.flush()
        session.expunge(plan)
    # Solo questo processo: negli altri lo stato vecchio scade entro `_CACHE_SECONDS`.
    _cache.pop((tenant, user_id), None)
    return _status_of(plan, user_id, now)


def require_usage_available(principal: AuthPrincipal = Depends(require_principal)) -> None:
    """Dipendenza FastAPI delle azioni dirette che spendono: il limite, prima di tutto.

    Il controllo sta al confine della rotta, prima che il servizio apra i suoi
    `try`: cosi' il 429 arriva al consulente col suo messaggio, e nessun
    servizio deve ricordarsi di lasciarlo passare. `require_principal` e' in
    cache per la richiesta: non si verifica il token due volte.
    """
    check(principal.user_id, tenant_id=principal.tenant_id)

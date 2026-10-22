"""SIM-28: previsto contro osservato per un'alternativa implementata.

Il consulente sceglie un'alternativa del workspace, il cliente la implementa in
una data. Dopo, con un log reale che copre il prima e il dopo (o due log), DeliR
misura quanto il simulatore aveva ragione: per ogni KPI la variazione prevista
(alternativa contro AS-IS, con il suo intervallo se c'erano ripetizioni) e la
variazione osservata (casi iniziati dopo contro casi iniziati prima).

Si confrontano variazioni relative, non valori: l'AS-IS simulato e il log del
prima possono differire in scala (il twin non e' perfetto), ma il cambiamento
che l'alternativa porta si legge sullo stesso metro. L'esito si calcola una
volta, quando si registra, e resta: e' il consuntivo della decisione.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.eventlog import storage as eventlog_storage
from backend.eventlog.service import EventLogNotFound, PeriodSummary, period_summary
from backend.schemas.simulation_scenarios import (
    OutcomeKpi,
    PredictedKpi,
    PutScenarioOutcomeRequest,
    ScenarioOutcomeKpi,
    ScenarioOutcomeLog,
    ScenarioOutcomeResponse,
)


def observed_value(summary: dict | None, kpi: OutcomeKpi) -> float | None:
    """Il KPI dal riassunto di un log; ``None`` se il log non lo sa (il costo senza colonna)."""
    if not summary:
        return None
    if kpi == "cycle":
        value = (summary.get("cycle") or {}).get("avg")
    elif kpi == "waiting":
        value = (summary.get("waiting") or {}).get("avg")
    elif kpi == "costPerCase":
        value = (summary.get("cost") or {}).get("perCase")
    else:
        value = summary.get("throughputPerHour")
    return float(value) if isinstance(value, int | float) else None


def compare(kpi: OutcomeKpi, predicted: PredictedKpi, before: float | None, after: float | None) -> ScenarioOutcomeKpi:
    delta = predicted.alternative - predicted.as_is
    change = delta / predicted.as_is
    low = high = None
    if predicted.half is not None:
        low, high = (delta - predicted.half) / predicted.as_is, (delta + predicted.half) / predicted.as_is
    observed = (after - before) / before if before and after is not None else None
    return ScenarioOutcomeKpi(
        kpi=kpi,
        predicted_change=change,
        predicted_low=low,
        predicted_high=high,
        before=before,
        after=after,
        observed_change=observed,
        error=observed - change if observed is not None else None,
        within=(low <= observed <= high) if observed is not None and low is not None and high is not None else None,
    )


def build_outcome(process_id: str, request: PutScenarioOutcomeRequest) -> ScenarioOutcomeResponse:
    """L'esito: KPI osservati prima e dopo la data, accanto alla previsione.

    Raises:
        ValueError: un log e' di un altro processo, non e' mappato o non ha casi nel periodo.
    """
    before = _period(process_id, request.before_event_log_id, "before", request)
    after = _period(process_id, request.after_event_log_id, "after", request)
    return ScenarioOutcomeResponse(
        implemented_on=request.implemented_on.isoformat(),
        recorded_at=datetime.now(UTC).isoformat(),
        as_is_run_id=request.as_is_run_id,
        alternative_run_id=request.alternative_run_id,
        before=ScenarioOutcomeLog(event_log_id=before.event_log.id, name=before.event_log.name, cases=before.cases),
        after=ScenarioOutcomeLog(event_log_id=after.event_log.id, name=after.event_log.name, cases=after.cases),
        kpis=[
            compare(kpi, predicted, observed_value(before.summary, kpi), observed_value(after.summary, kpi))
            for kpi, predicted in request.predicted.items()
        ],
    )


def _period(process_id: str, event_log_id: str, side: str, request: PutScenarioOutcomeRequest) -> PeriodSummary:
    log = eventlog_storage.get_event_log(event_log_id)
    if log is None or log.process_id != process_id:
        raise ValueError("Il log scelto non è di questo processo.")
    day = request.implemented_on
    try:
        summary = period_summary(event_log_id, before=day) if side == "before" else period_summary(event_log_id, since=day)
    except EventLogNotFound as exc:
        raise ValueError("Il log scelto non è di questo processo.") from exc
    if summary.cases == 0:
        when = "prima del" if side == "before" else "dal"
        raise ValueError(f"Nel log «{log.name}» nessun caso inizia {when} {day.strftime('%d/%m/%Y')}.")
    return summary

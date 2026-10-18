"""Experiment advisor — heuristic "what should I try next", no LLM.

Reads a completed run's full-log ``summary`` + the Prosimos ``scenario`` payload
and proposes concrete scenario changes, each with a *rough* estimate of the
cycle-time and cost impact. The headline experiment is "add one resource to the
pool behind the diagnostic bottleneck", sized with an M/M/c (Erlang-C) waiting
ratio.

Everything here is a back-of-the-envelope estimate — the UI labels it as such and
the real answer is always "run the scenario".
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExperimentEstimate(BaseModel):
    cycle_pct: float  # signed fraction, e.g. -0.42 == 42% faster
    cost_pct: float  # signed fraction


# SIM-22: cosa si prova sul collo di bottiglia. ``add_resource``: una risorsa in
# piu' nel suo pool. ``automate``: una quota del lavoro dell'attivita' fatta da
# un sistema (la durata scende di ``share``). ``reallocate``: una risorsa
# spostata da un pool poco usato (``donor_*``) a quello del collo di bottiglia.
ExperimentKind = Literal["add_resource", "automate", "reallocate"]

# Quanto lavoro toglie l'automazione proposta: meta', un primo passo credibile.
AUTOMATION_SHARE = 0.5
# Un pool che cede una risorsa deve restare sotto questo carico, altrimenti il
# collo di bottiglia si sposta li'.
DONOR_MAX_UTILIZATION = 0.85


class Experiment(BaseModel):
    kind: ExperimentKind
    pool_id: str
    pool_name: str
    from_amount: int
    to_amount: int
    rationale: str
    estimate: ExperimentEstimate
    # id of the bottleneck element the experiment targets
    target_el: str | None = None
    target_name: str | None = None
    # automate: la quota della durata che scompare.
    share: float | None = None
    # reallocate: il pool che cede una risorsa.
    donor_pool_id: str | None = None
    donor_pool_name: str | None = None
    donor_from_amount: int | None = None


class ExperimentReport(BaseModel):
    bottleneck_el: str | None = None
    bottleneck_name: str | None = None
    factors: dict[str, float] = Field(default_factory=dict)
    experiments: list[Experiment] = Field(default_factory=list)


def suggest_experiments(summary: dict | None, scenario: dict | None) -> ExperimentReport:
    if not summary:
        return ExperimentReport()

    bottleneck = summary.get("bottleneck") or {}
    b_el = bottleneck.get("el")
    b_name = bottleneck.get("name")
    report = ExperimentReport(
        bottleneck_el=b_el,
        bottleneck_name=b_name,
        factors={k: float(v) for k, v in (bottleneck.get("factors") or {}).items()},
    )
    if not b_el or not scenario:
        return report

    pool = _pool_for_task(scenario, b_el)
    if pool is None:
        return report

    c = max(1, int(pool["amount"]))
    lam = _arrival_rate(scenario)
    mu = _service_rate(scenario, b_el)
    if lam <= 0 or mu <= 0:
        return report

    wq_c = _mmc_wait(lam, mu, c)
    wq_c1 = _mmc_wait(lam, mu, c + 1)
    # `ratio` = wait that REMAINS after adding one server, 0..1.
    if wq_c == math.inf:
        # unstable at c: adding capacity is the difference between "never" and
        # a finite wait — treat the relief as near-total.
        ratio = 0.05 if math.isfinite(wq_c1) else 1.0
    elif wq_c > 0:
        ratio = min(1.0, max(0.0, wq_c1 / wq_c))
    else:
        ratio = 1.0  # no measurable queue to relieve

    cycle_avg = float(summary.get("cycle", {}).get("avg") or 0.0)
    b_wait = _bottleneck_wait_avg(summary, b_el)
    wait_share_of_cycle = (b_wait / cycle_avg) if cycle_avg > 0 else 0.0
    cycle_pct = -round(wait_share_of_cycle * (1.0 - ratio), 4)

    cost_pct = round(_pool_cost_share(scenario, pool["id"]) * (1.0 / c), 4)

    report.experiments.append(
        Experiment(
            kind="add_resource",
            pool_id=str(pool["id"]),
            pool_name=str(pool.get("name") or pool["id"]),
            from_amount=c,
            to_amount=c + 1,
            target_el=b_el,
            target_name=b_name,
            rationale=_rationale(c, wq_c, wait_share_of_cycle),
            estimate=ExperimentEstimate(cycle_pct=cycle_pct, cost_pct=cost_pct),
        )
    )

    donor = _donor_pool(summary, scenario, exclude=str(pool["id"]))
    if donor is not None:
        # Stessa coda in piu' del primo esperimento, a costo quasi invariato: cambia
        # solo la differenza fra il costo orario di chi arriva e di chi c'era.
        hourly = _hourly_cost(scenario)
        cost_shift = (pool["cost_per_hour"] - donor["cost_per_hour"]) / hourly if hourly > 0 else 0.0
        report.experiments.append(
            Experiment(
                kind="reallocate",
                pool_id=str(pool["id"]),
                pool_name=str(pool.get("name") or pool["id"]),
                from_amount=c,
                to_amount=c + 1,
                target_el=b_el,
                target_name=b_name,
                donor_pool_id=donor["id"],
                donor_pool_name=donor["name"],
                donor_from_amount=donor["amount"],
                rationale=(
                    f"{donor['name']} lavora al {round(donor['utilization'] * 100)}%: con una risorsa in meno "
                    f"resta al {round(donor['after'] * 100)}%. Vale solo se quella persona sa fare il lavoro."
                ),
                estimate=ExperimentEstimate(cycle_pct=cycle_pct, cost_pct=round(cost_shift, 4)),
            )
        )

    # Automazione: il servizio dura (1 - share), la coda si calcola con mu / (1 - share).
    wq_auto = _mmc_wait(lam, mu / (1 - AUTOMATION_SHARE), c)
    if wq_c == math.inf:
        auto_ratio = 0.05 if math.isfinite(wq_auto) else 1.0
    elif wq_c > 0:
        auto_ratio = min(1.0, max(0.0, wq_auto / wq_c))
    else:
        auto_ratio = 1.0
    proc_share = _activity_processing_share(summary, b_el, cycle_avg)
    activity_cost_share = _activity_cost_share(summary, b_el)
    report.experiments.append(
        Experiment(
            kind="automate",
            pool_id=str(pool["id"]),
            pool_name=str(pool.get("name") or pool["id"]),
            from_amount=c,
            to_amount=c,
            target_el=b_el,
            target_name=b_name,
            share=AUTOMATION_SHARE,
            rationale=(
                f"Se un sistema fa la meta' del lavoro di {b_name or b_el}, si accorcia la lavorazione e "
                "la coda scende con lei. Il costo del sistema non e' nella stima."
            ),
            estimate=ExperimentEstimate(
                cycle_pct=-round(wait_share_of_cycle * (1.0 - auto_ratio) + proc_share * AUTOMATION_SHARE, 4),
                cost_pct=-round(activity_cost_share * AUTOMATION_SHARE, 4),
            ),
        )
    )
    return report


def _donor_pool(summary: dict, scenario: dict, *, exclude: str) -> dict | None:
    """Il pool meno carico che puo' cedere una risorsa restando sotto ``DONOR_MAX_UTILIZATION``."""
    utilization: dict[str, list[float]] = {}
    for row in summary.get("byResource") or []:
        utilization.setdefault(str(row.get("pool") or ""), []).append(_num(row.get("utilizationPct"), 0.0) / 100)
    best: dict | None = None
    for profile in scenario.get("resource_profiles") or []:
        pid = str(profile.get("id"))
        name = str(profile.get("name") or pid)
        if pid == exclude:
            continue
        amount = int(sum(_num(res.get("amount"), 1) for res in profile.get("resource_list") or []))
        loads = utilization.get(name) or utilization.get(pid)
        if amount < 2 or not loads:
            continue
        load = sum(loads) / len(loads)
        after = load * amount / (amount - 1)
        if after >= DONOR_MAX_UTILIZATION:
            continue
        cost = max((_num(res.get("cost_per_hour"), 0.0) for res in profile.get("resource_list") or []), default=0.0)
        if best is None or load < best["utilization"]:
            best = {"id": pid, "name": name, "amount": amount, "utilization": load, "after": after, "cost_per_hour": cost}
    return best


def _hourly_cost(scenario: dict) -> float:
    return sum(
        _num(res.get("amount"), 1) * _num(res.get("cost_per_hour"), 0.0)
        for profile in scenario.get("resource_profiles") or []
        for res in profile.get("resource_list") or []
    )


def _activity_row(summary: dict, el: str) -> dict:
    return next((row for row in summary.get("byActivity") or [] if row.get("el") == el), {})


def _activity_processing_share(summary: dict, el: str, cycle_avg: float) -> float:
    """Quota del tempo di attraversamento spesa a lavorare sull'attivita'."""
    row = _activity_row(summary, el)
    cases = _num(summary.get("casesCompleted"), 0.0)
    count = _num(row.get("count"), 0.0)
    if cycle_avg <= 0 or cases <= 0:
        return 0.0
    per_case = _num((row.get("processing") or {}).get("avg"), 0.0) * count / cases
    return min(1.0, per_case / cycle_avg)


def _activity_cost_share(summary: dict, el: str) -> float:
    row = _activity_row(summary, el)
    total = _num((summary.get("cost") or {}).get("total"), 0.0)
    spent = _num(row.get("avgCost"), 0.0) * _num(row.get("count"), 0.0)
    return min(1.0, spent / total) if total > 0 else 0.0


# --- M/M/c ---------------------------------------------------------------


def _mmc_wait(lam: float, mu: float, c: int) -> float:
    """Erlang-C mean waiting time in queue. inf when the system is unstable."""
    rho = lam / (c * mu)
    if rho >= 1.0:
        return math.inf
    a = lam / mu  # offered load
    # P0
    sum_terms = sum(a**k / math.factorial(k) for k in range(c))
    last = (a**c / math.factorial(c)) * (1.0 / (1.0 - rho))
    p0 = 1.0 / (sum_terms + last)
    p_wait = last * p0
    return p_wait / (c * mu - lam)


# --- scenario payload readers -----------------------------------------


def _arrival_rate(scenario: dict) -> float:
    dist = scenario.get("arrival_time_distribution") or {}
    mean = _mean_of(dist)
    return (1.0 / mean) if mean and mean > 0 else 0.0


def _service_rate(scenario: dict, task_el: str) -> float:
    for row in scenario.get("task_resource_distribution") or []:
        if row.get("task_id") != task_el:
            continue
        resources = row.get("resources") or []
        if not resources:
            return 0.0
        mean = _mean_of(resources[0])
        return (1.0 / mean) if mean and mean > 0 else 0.0
    return 0.0


def _pool_for_task(scenario: dict, task_el: str) -> dict | None:
    resource_id: str | None = None
    for row in scenario.get("task_resource_distribution") or []:
        if row.get("task_id") == task_el:
            resources = row.get("resources") or []
            if resources:
                resource_id = resources[0].get("resource_id")
            break
    for profile in scenario.get("resource_profiles") or []:
        for res in profile.get("resource_list") or []:
            if resource_id is not None and res.get("id") == resource_id:
                return {
                    "id": profile.get("id") or res.get("id"),
                    "name": profile.get("name") or res.get("name"),
                    "amount": _num(res.get("amount"), 1),
                    "cost_per_hour": _num(res.get("cost_per_hour"), 0.0),
                }
            if resource_id is None and task_el in (res.get("assignedTasks") or []):
                return {
                    "id": profile.get("id") or res.get("id"),
                    "name": profile.get("name") or res.get("name"),
                    "amount": _num(res.get("amount"), 1),
                    "cost_per_hour": _num(res.get("cost_per_hour"), 0.0),
                }
    return None


def _pool_cost_share(scenario: dict, pool_id: str) -> float:
    totals: dict[str, float] = {}
    for profile in scenario.get("resource_profiles") or []:
        pid = str(profile.get("id"))
        for res in profile.get("resource_list") or []:
            totals[pid] = totals.get(pid, 0.0) + _num(res.get("amount"), 1) * _num(
                res.get("cost_per_hour"), 0.0
            )
    grand = sum(totals.values())
    return (totals.get(str(pool_id), 0.0) / grand) if grand > 0 else 1.0


def _bottleneck_wait_avg(summary: dict, el: str) -> float:
    for row in summary.get("byActivity") or []:
        if row.get("el") == el:
            return _num((row.get("wait") or {}).get("avg"), 0.0)
    return 0.0


def _rationale(c: int, wq_c: float, wait_share: float) -> str:
    if wq_c == math.inf:
        return (
            f"La coda su questo passaggio cresce senza limite con {c} "
            f"{'risorsa' if c == 1 else 'risorse'}: la capacità non regge il volume."
        )
    return (
        f"{c} {'risorsa assorbe' if c == 1 else 'risorse assorbono'} circa il "
        f"{round(wait_share * 100)}% del tempo di attraversamento in attesa."
    )


def _mean_of(distribution: dict) -> float:
    """La media di una distribuzione compilata per Prosimos.

    Il primo parametro e' la media (o il valore fisso) per tutte le
    distribuzioni tranne l'uniforme, che ha solo minimo e massimo
    (``ir.compile.distribution_params``).
    """
    params = distribution.get("distribution_params") or []
    if distribution.get("distribution_name") == "uniform":
        values = [_num(p.get("value"), 0.0) for p in params[:2] if isinstance(p, dict)]
        return sum(values) / 2 if len(values) == 2 else 0.0
    return _first_value(params)


def _first_value(params: list[Any]) -> float:
    for p in params:
        if isinstance(p, dict) and "value" in p:
            return _num(p["value"], 0.0)
    return 0.0


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

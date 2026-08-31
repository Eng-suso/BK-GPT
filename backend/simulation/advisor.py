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


class Experiment(BaseModel):
    kind: Literal["add_resource"]
    pool_id: str
    pool_name: str
    from_amount: int
    to_amount: int
    rationale: str
    estimate: ExperimentEstimate
    # id of the bottleneck element the experiment targets
    target_el: str | None = None


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
            rationale=_rationale(c, wq_c, wait_share_of_cycle),
            estimate=ExperimentEstimate(cycle_pct=cycle_pct, cost_pct=cost_pct),
        )
    )
    return report


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
    params = dist.get("distribution_params") or []
    mean = _first_value(params)
    return (1.0 / mean) if mean and mean > 0 else 0.0


def _service_rate(scenario: dict, task_el: str) -> float:
    for row in scenario.get("task_resource_distribution") or []:
        if row.get("task_id") != task_el:
            continue
        resources = row.get("resources") or []
        if not resources:
            return 0.0
        params = resources[0].get("distribution_params") or []
        mean = _first_value(params)
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

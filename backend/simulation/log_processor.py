"""Turn a Prosimos run (statistics payload + full simulation event log) into the
two things the DeliR simulation section needs:

1. ``summary``  — every reported KPI / percentile / queue statistic / bottleneck.
   Computed from the **full** event log (plus Prosimos' own decoded statistics for
   the figures it already computes well, e.g. resource utilisation with calendars).
   This is the single source of truth for anything shown as a number.

2. ``replay``   — a compact *display representation*: a deterministic sample of
   case paths (for token animation), a bucketed time series (for the live
   dashboard) and sequence-flow volumes (for system mode). Never a metric source.

Architectural rule: no percentile / KPI is ever derived from the sampled cases.
Changing ``sim_replay_max_cases`` must not move a single number in ``summary``.
"""
from __future__ import annotations

import csv
import io
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from backend.settings import settings

EXPECTED_LOG_HEADER = [
    "case_id",
    "activity",
    "enable_time",
    "start_time",
    "end_time",
    "resource",
]

# A wait below this doesn't count as "queued" for cases-affected / bottleneck.
_QUEUE_EPSILON_SEC = 60.0
_INSTANCE_SUFFIX = re.compile(r"_\d+$")


class ProsimosLogError(ValueError):
    """Raised when the event log can't be parsed into the expected shape."""


@dataclass(slots=True)
class LogEvent:
    case_id: str
    activity: str
    enable: float  # epoch seconds
    start: float
    end: float
    resource: str


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def _parse_ts(raw: str) -> float:
    # Prosimos: "2026-01-05 09:00:00.000000+00:00"
    return datetime.fromisoformat(raw.strip()).timestamp()


def parse_prosimos_log(csv_text: str) -> list[LogEvent]:
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise ProsimosLogError("empty Prosimos event log") from exc

    if header != EXPECTED_LOG_HEADER:
        raise ProsimosLogError(f"unexpected Prosimos log header: {header!r}")

    events: list[LogEvent] = []
    for row in reader:
        if len(row) != 6 or not row[0].strip():
            continue
        try:
            events.append(
                LogEvent(
                    case_id=row[0].strip(),
                    activity=row[1].strip(),
                    enable=_parse_ts(row[2]),
                    start=_parse_ts(row[3]),
                    end=_parse_ts(row[4]),
                    resource=row[5].strip(),
                )
            )
        except ValueError as exc:
            raise ProsimosLogError(f"bad Prosimos log row {row!r}: {exc}") from exc

    if not events:
        raise ProsimosLogError("Prosimos event log has a header but no data rows")
    return events


def activity_name_to_element_id(normalized_bpmn_xml: str) -> dict[str, str]:
    """Map the activity *name* Prosimos writes in the log to its BPMN element id.
    First occurrence wins for duplicate names (they can't be disambiguated)."""
    from backend.simulation.scenario_builder import parse_bpmn_for_simulation

    mapping: dict[str, str] = {}
    try:
        tasks, _gateways = parse_bpmn_for_simulation(normalized_bpmn_xml)
    except ValueError:
        return mapping
    for task in tasks:
        mapping.setdefault(task.name, task.id)
    return mapping


# --------------------------------------------------------------------------- #
# small numeric helpers (numpy-free — the log streams, we don't want big arrays)
# --------------------------------------------------------------------------- #

def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (rank - low)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _time_weighted_queue(spans: list[tuple[float, float]], t0: float, t1: float) -> tuple[float, int]:
    """avg and max concurrent count over [t0, t1] given (enter, leave) spans."""
    if not spans or t1 <= t0:
        return 0.0, 0
    deltas: list[tuple[float, int]] = []
    for enter, leave in spans:
        deltas.append((max(enter, t0), 1))
        deltas.append((min(leave, t1), -1))
    deltas.sort()
    area = 0.0
    peak = 0
    depth = 0
    cursor = t0
    for when, change in deltas:
        when = min(max(when, t0), t1)
        if when > cursor:
            area += depth * (when - cursor)
            cursor = when
        depth += change
        peak = max(peak, depth)
    return area / (t1 - t0), peak


# --------------------------------------------------------------------------- #
# Prosimos statistics payload (already json-decoded by the adapter)
# --------------------------------------------------------------------------- #

def _records(value: object) -> list[dict]:
    """Coerce a (possibly still multiply-encoded) Prosimos stats section to rows."""
    import json

    current = value
    for _ in range(4):
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (ValueError, TypeError):
                break
        else:
            break
    if isinstance(current, list):
        return [row for row in current if isinstance(row, dict)]
    return []


def _num(value: object) -> float:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return num if math.isfinite(num) else 0.0


def _overall_avg(rows: list[dict], kpi: str) -> tuple[float, int]:
    for row in rows:
        if str(row.get("KPI")) == kpi:
            return _num(row.get("Average")), int(_num(row.get("Trace Ocurrences")))
    return 0.0, 0


# --------------------------------------------------------------------------- #
# scenario payload -> resource pools (amounts + cost)
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class Pool:
    id: str
    name: str
    amount: int
    cost_per_hour: float


def _pools_from_scenario(scenario_payload: dict) -> dict[str, Pool]:
    """Map the *instance name* Prosimos writes in the log (``Operatore_0``) to its
    logical pool. Keyed by the de-suffixed name."""
    pools: dict[str, Pool] = {}
    for profile in scenario_payload.get("resource_profiles", []):
        for res in profile.get("resource_list", []):
            name = str(res.get("name", "")).strip()
            if not name:
                continue
            pools[name] = Pool(
                id=str(res.get("id", name)),
                name=name,
                amount=max(1, int(_num(res.get("amount")) or 1)),
                cost_per_hour=_num(res.get("cost_per_hour")),
            )
    return pools


def _pool_key(resource_instance: str) -> str:
    return _INSTANCE_SUFFIX.sub("", resource_instance)


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #

def process_prosimos_log(
    csv_text: str,
    *,
    normalized_bpmn_xml: str,
    scenario_payload: dict,
    prosimos_stats: dict,
    name_to_element_id: dict[str, str] | None = None,
    max_cases: int | None = None,
    buckets: int | None = None,
) -> tuple[dict, dict]:
    events = parse_prosimos_log(csv_text)
    max_cases = max_cases or settings.sim_replay_max_cases
    buckets = buckets or settings.sim_replay_buckets

    name_to_element_id = name_to_element_id or {}
    run_start = min(ev.enable for ev in events)
    run_end = max(ev.end for ev in events)
    duration = max(1.0, run_end - run_start)

    by_case: dict[str, list[LogEvent]] = defaultdict(list)
    by_activity: dict[str, list[LogEvent]] = defaultdict(list)
    for ev in events:
        by_case[ev.case_id].append(ev)
        by_activity[ev.activity].append(ev)

    pools = _pools_from_scenario(scenario_payload)
    activity_cost = {
        str(r.get("Name")): _num(r.get("Total Cost"))
        for r in _records(prosimos_stats.get("IndividualTaskStatistics"))
    }

    summary = _build_summary(
        events=events,
        by_case=by_case,
        by_activity=by_activity,
        name_to_element_id=name_to_element_id,
        prosimos_stats=prosimos_stats,
        pools=pools,
        run_start=run_start,
        run_end=run_end,
        duration=duration,
    )
    replay = _build_replay(
        events=events,
        by_case=by_case,
        by_activity=by_activity,
        name_to_element_id=name_to_element_id,
        normalized_bpmn_xml=normalized_bpmn_xml,
        pools=pools,
        activity_cost=activity_cost,
        run_start=run_start,
        duration=duration,
        max_cases=max_cases,
        buckets=buckets,
    )
    return summary, replay


# --------------------------------------------------------------------------- #
# (1) summary — full-log KPIs
# --------------------------------------------------------------------------- #

def _build_summary(
    *,
    events: list[LogEvent],
    by_case: dict[str, list[LogEvent]],
    by_activity: dict[str, list[LogEvent]],
    name_to_element_id: dict[str, str],
    prosimos_stats: dict,
    pools: dict[str, Pool],
    run_start: float,
    run_end: float,
    duration: float,
) -> dict:
    overall = _records(prosimos_stats.get("OverallScenarioStatistics"))
    task_rows = {str(r.get("Name")): r for r in _records(prosimos_stats.get("IndividualTaskStatistics"))}
    resource_rows = _records(prosimos_stats.get("ResourceUtilization"))

    # Wall-clock KPIs from the full log. The event log only carries wall times, so
    # DeliR reports elapsed time ("quanto impiega un ordine") — which is also the
    # clean decomposition cycle == waiting + processing. Prosimos' own
    # calendar-active `cycle_time`/`processing_time` are kept only as a cross-check.
    cycles: list[float] = []
    waits: list[float] = []
    procs: list[float] = []
    case_cycle_total = 0.0
    for case_events in by_case.values():
        first_enable = min(ev.enable for ev in case_events)
        last_end = max(ev.end for ev in case_events)
        cycle = max(0.0, last_end - first_enable)
        cycles.append(cycle)
        waits.append(sum(max(0.0, ev.start - ev.enable) for ev in case_events))
        procs.append(sum(max(0.0, ev.end - ev.start) for ev in case_events))
        case_cycle_total += cycle
    cycles.sort()
    waits.sort()
    procs.sort()

    cases_completed = len(by_case)
    _, trace_occ = _overall_avg(overall, "cycle_time")
    cycle_avg = _mean(cycles)
    wait_avg = _mean(waits)
    proc_avg = _mean(procs)

    # Cost = active work time × rate — take Prosimos' per-activity totals (they use
    # calendar-active processing, which is the right billing basis).
    total_cost = sum(_num(r.get("Total Cost")) for r in task_rows.values())

    active_span_hours = max(1e-9, (run_end - run_start) / 3600.0)
    throughput_per_hour = cases_completed / active_span_hours

    by_activity_out: list[dict] = []
    for name, act_events in by_activity.items():
        act_waits = sorted(max(0.0, ev.start - ev.enable) for ev in act_events)
        spans = [(ev.enable, ev.start) for ev in act_events]
        queue_avg, queue_max = _time_weighted_queue(spans, run_start, run_end)
        act_wait_total = sum(act_waits)
        act_proc_total = sum(max(0.0, ev.end - ev.start) for ev in act_events)
        affected_cases = {
            ev.case_id for ev in act_events if (ev.start - ev.enable) > _QUEUE_EPSILON_SEC
        }
        prosimos_row = task_rows.get(name, {})
        by_activity_out.append(
            {
                "el": name_to_element_id.get(name),
                "name": name,
                "count": len(act_events),
                "wait": {
                    "avg": _mean(act_waits),
                    "p95": _percentile(act_waits, 95),
                },
                "queue": {"avg": round(queue_avg, 3), "max": queue_max},
                "avgCost": _num(prosimos_row.get("Avg Cost")),
                "cycleContributionPct": round(
                    (act_wait_total + act_proc_total) / case_cycle_total, 4
                )
                if case_cycle_total
                else 0.0,
                "casesAffectedPct": round(len(affected_cases) / cases_completed, 4)
                if cases_completed
                else 0.0,
            }
        )
    by_activity_out.sort(key=lambda row: row["wait"]["avg"], reverse=True)

    by_resource_out: list[dict] = []
    for index, row in enumerate(resource_rows):
        by_resource_out.append(
            {
                "id": str(row.get("Resource ID", f"resource-{index}")),
                "name": str(row.get("Resource name", row.get("Resource ID", "—"))),
                "pool": str(row.get("Pool name", "")),
                "utilizationPct": round(_num(row.get("Utilization Ratio")) * 100),
            }
        )

    bottleneck = _diagnose_bottleneck(
        by_activity_out,
        by_resource_out,
        by_activity=by_activity,
        run_start=run_start,
        run_end=run_end,
        total_wait=sum(waits),
    )

    px_cycle, _ = _overall_avg(overall, "idle_cycle_time")
    px_wait, _ = _overall_avg(overall, "waiting_time")

    return {
        "casesCompleted": cases_completed or trace_occ,
        "cycle": {
            "avg": cycle_avg,
            "p50": _percentile(cycles, 50),
            "p90": _percentile(cycles, 90),
            "p95": _percentile(cycles, 95),
        },
        "waiting": {
            "avg": wait_avg,
            "p95": _percentile(waits, 95),
            "share": round(wait_avg / cycle_avg, 4) if cycle_avg else 0.0,
        },
        "processing": {"avg": proc_avg, "p95": _percentile(procs, 95)},
        "cost": {
            "total": total_cost,
            "perCase": total_cost / cases_completed if cases_completed else 0.0,
        },
        "throughputPerHour": round(throughput_per_hour, 3),
        "byActivity": by_activity_out,
        "byResource": by_resource_out,
        "bottleneck": bottleneck,
        # Prosimos' own end-of-run figures — a cross-check, never displayed as the
        # headline (they use a different, calendar-active basis).
        "prosimosCrossCheck": {"idleCycleAvg": px_cycle, "waitingAvg": px_wait},
    }


def _diagnose_bottleneck(
    by_activity_out: list[dict],
    by_resource_out: list[dict],
    *,
    by_activity: dict[str, list[LogEvent]],
    run_start: float,
    run_end: float,
    total_wait: float,
) -> dict | None:
    """Multi-factor, full-log verdict — distinct from the replay's live 'pressure'
    badge. Score each activity on 6 normalised factors and take the max."""
    if not by_activity_out or total_wait <= 0:
        return None

    # utilisation per logical pool ("Operatore"), from Prosimos' calendar-aware stats
    util_by_pool: dict[str, float] = {}
    for row in by_resource_out:
        pool = row["pool"] or _pool_key(row["name"])
        util_by_pool[pool] = max(util_by_pool.get(pool, 0.0), row["utilizationPct"] / 100.0)

    best: dict | None = None
    for row in by_activity_out:
        act_events = by_activity.get(row["name"], [])
        act_wait_total = sum(max(0.0, ev.start - ev.enable) for ev in act_events)
        act_pools = {_pool_key(ev.resource) for ev in act_events}
        act_utilization = max((util_by_pool.get(p, 0.0) for p in act_pools), default=0.0)

        # persistence: fraction of the run where this activity's queue was non-empty
        spans = sorted((ev.enable, ev.start) for ev in act_events if ev.start > ev.enable)
        busy = 0.0
        cursor = run_start
        depth_end = cursor
        for enter, leave in spans:
            if leave <= depth_end:
                depth_end = max(depth_end, leave)
                continue
            busy += leave - max(enter, depth_end)
            depth_end = leave
        persistence = min(1.0, busy / max(1.0, run_end - run_start))

        # queue growth: is the second half's mean queue bigger than the first half?
        mid = (run_start + run_end) / 2
        first = _time_weighted_queue([(e, s) for e, s in spans], run_start, mid)[0]
        second = _time_weighted_queue([(e, s) for e, s in spans], mid, run_end)[0]
        growth = 0.0 if first + second == 0 else max(0.0, (second - first) / (first + second))

        factors = {
            "waitingContribution": round(act_wait_total / total_wait, 4),
            "utilization": round(act_utilization, 4),
            "queueGrowth": round(growth, 4),
            "casesAffected": row["casesAffectedPct"],
            "cycleContribution": row["cycleContributionPct"],
            "persistence": round(persistence, 4),
        }
        score = (
            0.30 * factors["waitingContribution"]
            + 0.20 * factors["utilization"]
            + 0.15 * factors["queueGrowth"]
            + 0.10 * factors["casesAffected"]
            + 0.15 * factors["cycleContribution"]
            + 0.10 * factors["persistence"]
        )
        if best is None or score > best["score"]:
            best = {"el": row["el"], "name": row["name"], "score": round(score, 4), "factors": factors}

    if best and best["score"] >= 0.15:
        return best
    return None


# --------------------------------------------------------------------------- #
# (2) replay — display representation
# --------------------------------------------------------------------------- #

def _build_replay(
    *,
    events: list[LogEvent],
    by_case: dict[str, list[LogEvent]],
    by_activity: dict[str, list[LogEvent]],
    name_to_element_id: dict[str, str],
    normalized_bpmn_xml: str,
    pools: dict[str, Pool],
    activity_cost: dict[str, float],
    run_start: float,
    duration: float,
    max_cases: int,
    buckets: int,
) -> dict:
    from bisect import bisect_right
    from datetime import UTC

    from backend.simulation.flow_graph import build_flow_graph

    # `buckets` intervals -> `buckets + 1` sample points spanning [0, duration],
    # so the last point reflects the fully-finished run (done == totalCases).
    run_end = run_start + duration
    bucket_sec = max(1.0, duration / buckets)
    points = buckets + 1
    # clamp the final point to exactly `duration` so the last sample is the
    # fully-finished run despite float accumulation.
    t_axis = [round(min(i * bucket_sec, duration), 3) for i in range(points)]
    query = [min(run_start + i * bucket_sec, run_end) for i in range(points)]

    def counts_at(sorted_ts: list[float]) -> list[int]:
        return [bisect_right(sorted_ts, t) for t in query]

    elements_meta = {
        name_to_element_id[name]: {"name": name}
        for name in by_activity
        if name in name_to_element_id
    }

    # ---- per-element series via edge counts (O(elements * buckets log n)) --
    series_by_element: dict[str, dict[str, list[float]]] = {}
    for name, act_events in by_activity.items():
        el = name_to_element_id.get(name)
        if el is None:
            continue
        enables = sorted(ev.enable for ev in act_events)
        starts = sorted(ev.start for ev in act_events)
        ends = sorted(ev.end for ev in act_events)
        c_enable, c_start, c_end = counts_at(enables), counts_at(starts), counts_at(ends)
        series_by_element[el] = {
            "active": [c_start[i] - c_end[i] for i in range(points)],
            "queued": [c_enable[i] - c_start[i] for i in range(points)],
            "done": [float(c_end[i]) for i in range(points)],
        }

    # ---- per-resource (pool) busy fraction -------------------------------
    pool_events: dict[str, list[LogEvent]] = defaultdict(list)
    for ev in events:
        pool_events[_pool_key(ev.resource)].append(ev)
    series_by_resource: dict[str, dict[str, list[float]]] = {}
    for key, evs in pool_events.items():
        amount = max(1, pools.get(key, Pool(key, key, 1, 0.0)).amount)
        starts = sorted(ev.start for ev in evs)
        ends = sorted(ev.end for ev in evs)
        c_start, c_end = counts_at(starts), counts_at(ends)
        series_by_resource[key] = {
            "busy": [round(min(1.0, (c_start[i] - c_end[i]) / amount), 4) for i in range(points)]
        }

    # ---- global series --------------------------------------------------
    case_bounds = {
        cid: (min(ev.enable for ev in evs), max(ev.end for ev in evs))
        for cid, evs in by_case.items()
    }
    first_enables = sorted(b[0] for b in case_bounds.values())
    last_ends = sorted(b[1] for b in case_bounds.values())
    ends_with_cycle = sorted((e, e - s) for s, e in case_bounds.values())
    prefix_cycle = [0.0]
    for _end, cyc in ends_with_cycle:
        prefix_cycle.append(prefix_cycle[-1] + cyc)
    sorted_ends_only = [e for e, _c in ends_with_cycle]

    c_enter = counts_at(first_enables)
    c_done = counts_at(last_ends)
    g_wip = [float(c_enter[i] - c_done[i]) for i in range(points)]
    g_done = [float(c_done[i]) for i in range(points)]
    g_queued = [
        sum(col["queued"][i] for col in series_by_element.values()) for i in range(points)
    ]
    g_cycle = []
    for i in range(points):
        n = bisect_right(sorted_ends_only, query[i])
        g_cycle.append(round(prefix_cycle[n] / n, 2) if n else 0.0)

    throughput_per_hour = [
        round((g_done[i] - (g_done[i - 1] if i else 0.0)) / (bucket_sec / 3600.0), 3)
        for i in range(points)
    ]

    # Cost accrued: distribute each activity's Prosimos Total Cost across its
    # instances by wall-processing weight, accumulate by finish time. This makes
    # the curve converge to summary.cost.total rather than to a wall-clock recompute.
    wall_proc_total: dict[str, float] = defaultdict(float)
    for ev in events:
        wall_proc_total[ev.activity] += max(0.0, ev.end - ev.start)
    finished = sorted(events, key=lambda ev: ev.end)
    g_cost = [0.0] * points
    acc = 0.0
    ptr = 0
    for i in range(points):
        t = query[i]
        while ptr < len(finished) and finished[ptr].end <= t:
            ev = finished[ptr]
            denom = wall_proc_total.get(ev.activity) or 1.0
            share = max(0.0, ev.end - ev.start) / denom
            acc += activity_cost.get(ev.activity, 0.0) * share
            ptr += 1
        g_cost[i] = round(acc, 2)

    # ---- sampled cases (DISPLAY ONLY) -----------------------------------
    sample = _sample_cases(by_case, case_bounds, max_cases)
    cases_out = []
    for cid in sample:
        evs = sorted(by_case[cid], key=lambda e: e.start)
        first_enable = min(e.enable for e in evs)
        cases_out.append(
            {
                "id": cid,
                "cycleSec": round(max(e.end for e in evs) - first_enable, 2),
                "events": [
                    {
                        "el": name_to_element_id.get(e.activity),
                        "enable": round(e.enable - run_start, 2),
                        "start": round(e.start - run_start, 2),
                        "end": round(e.end - run_start, 2),
                        "res": _pool_key(e.resource),
                    }
                    for e in evs
                ],
            }
        )

    # ---- flow volumes -------------------------------------------------
    flows = _flow_volumes(by_case, build_flow_graph(normalized_bpmn_xml), name_to_element_id)

    return {
        "schemaVersion": settings.sim_replay_schema_version,
        "meta": {
            "start": datetime.fromtimestamp(run_start, tz=UTC).isoformat(),
            "durationSec": round(duration, 2),
            "totalCases": len(by_case),
            "sampledCases": len(cases_out),
            "bucketSec": round(bucket_sec, 3),
        },
        "elements": elements_meta,
        "cases": cases_out,
        "series": {
            "t": t_axis,
            "byElement": series_by_element,
            "byResource": series_by_resource,
            "global": {
                "wip": g_wip,
                "queued": g_queued,
                "done": g_done,
                "throughputPerHour": throughput_per_hour,
                "costAccrued": g_cost,
                "avgCycleSec": g_cycle,
            },
        },
        "flows": flows,
    }


def _sample_cases(
    by_case: dict[str, list[LogEvent]],
    case_bounds: dict[str, tuple[float, float]],
    max_cases: int,
) -> list[str]:
    ids = list(by_case)
    if len(ids) <= max_cases:
        return ids

    def _key(cid: str) -> tuple[int, str]:
        return (0, f"{int(cid):020d}") if cid.isdigit() else (1, cid)

    ordered = sorted(ids, key=_key)
    cycles = {cid: case_bounds[cid][1] - case_bounds[cid][0] for cid in ordered}
    by_cycle = sorted(ordered, key=lambda c: cycles[c])
    must_have = {by_cycle[0], by_cycle[len(by_cycle) // 2], by_cycle[-1]}

    stride = len(ordered) / (max_cases - len(must_have))
    picked = {ordered[min(len(ordered) - 1, int(i * stride))] for i in range(max_cases)}
    picked |= must_have
    return [cid for cid in ordered if cid in picked][:max_cases]


def _flow_volumes(
    by_case: dict[str, list[LogEvent]],
    graph,
    name_to_element_id: dict[str, str],
) -> dict[str, dict]:
    id_by_name = name_to_element_id
    transitions: dict[tuple[str, str], int] = defaultdict(int)
    for evs in by_case.values():
        ordered = sorted(evs, key=lambda e: e.start)
        for a, b in zip(ordered, ordered[1:]):
            src = id_by_name.get(a.activity)
            dst = id_by_name.get(b.activity)
            if src and dst:
                transitions[(src, dst)] += 1

    flow_counts: dict[str, int] = defaultdict(int)
    for (src, dst), count in transitions.items():
        path = graph.unique_flow_path(src, dst)
        if path:
            for flow_id in path:
                flow_counts[flow_id] += count
        # ambiguous / unresolvable transitions contribute nothing to `flows`;
        # System Mode falls back to node-level active/queued chips.

    return {
        flow_id: {"count": count, "attributed": True}
        for flow_id, count in sorted(flow_counts.items())
    }

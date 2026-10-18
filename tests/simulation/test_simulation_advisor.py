"""Phase 9 — experiment advisor (M/M/c heuristic, no LLM)."""

import math

from backend.simulation.advisor import _mmc_wait, suggest_experiments


def _scenario(*, arrival_mean=200.0, service_mean=300.0, amount=1, cost=35.0):
    return {
        "arrival_time_distribution": {
            "distribution_name": "expon",
            "distribution_params": [{"value": arrival_mean}, {"value": 0.0}],
        },
        "task_resource_distribution": [
            {
                "task_id": "Task_Review",
                "resources": [
                    {
                        "resource_id": "res-1",
                        "distribution_name": "norm",
                        "distribution_params": [{"value": service_mean}],
                    }
                ],
            }
        ],
        "resource_profiles": [
            {
                "id": "pool-ops",
                "name": "Back office",
                "resource_list": [
                    {
                        "id": "res-1",
                        "name": "Operatore",
                        "amount": amount,
                        "cost_per_hour": str(cost),
                        "assignedTasks": ["Task_Review"],
                    }
                ],
            }
        ],
    }


def _summary(*, bottleneck_el="Task_Review", wait_avg=4000.0, cycle_avg=6000.0):
    return {
        "cycle": {"avg": cycle_avg},
        "waiting": {"avg": wait_avg, "share": wait_avg / cycle_avg},
        "byActivity": [
            {"el": "Task_Review", "name": "Verifica", "wait": {"avg": wait_avg}},
            {"el": "Task_Approve", "name": "Approva", "wait": {"avg": 200.0}},
        ],
        "bottleneck": {
            "el": bottleneck_el,
            "name": "Verifica",
            "score": 0.4,
            "factors": {"utilization": 0.98, "waitingContribution": 0.7},
        },
    }


def test_mmc_wait_is_infinite_when_unstable_and_shrinks_with_servers():
    # λ > c·μ  -> unstable
    assert _mmc_wait(1 / 100, 1 / 300, 1) == math.inf
    w2 = _mmc_wait(1 / 100, 1 / 300, 4)
    w3 = _mmc_wait(1 / 100, 1 / 300, 5)
    assert math.isfinite(w2) and w3 < w2


def test_suggests_adding_a_server_to_the_bottleneck_pool():
    report = suggest_experiments(_summary(), _scenario(amount=1))
    assert report.bottleneck_el == "Task_Review"
    # Un solo pool: si aggiunge o si automatizza, non c'e' da chi spostare.
    assert [e.kind for e in report.experiments] == ["add_resource", "automate"]
    exp = report.experiments[0]
    assert exp.kind == "add_resource"
    assert exp.pool_id == "pool-ops"
    assert exp.from_amount == 1 and exp.to_amount == 2
    # unstable at 1 server -> a big cycle improvement, a positive cost delta
    assert exp.estimate.cycle_pct < 0
    assert exp.estimate.cost_pct > 0
    assert exp.target_el == "Task_Review"


def test_stable_system_gives_a_smaller_estimate():
    # plenty of capacity already: arrival slow, service fast, 3 servers
    report = suggest_experiments(
        _summary(wait_avg=300.0, cycle_avg=6000.0),
        _scenario(arrival_mean=600.0, service_mean=120.0, amount=3),
    )
    exp = report.experiments[0]
    assert -0.1 < exp.estimate.cycle_pct <= 0


def test_no_experiments_without_a_bottleneck_or_scenario():
    assert suggest_experiments(None, None).experiments == []
    assert suggest_experiments({"bottleneck": None}, _scenario()).experiments == []
    assert suggest_experiments(_summary(), None).experiments == []


def test_cost_share_splits_across_pools():
    scenario = _scenario(amount=2, cost=40.0)
    scenario["resource_profiles"].append(
        {
            "id": "pool-mgr",
            "name": "Responsabili",
            "resource_list": [
                {"id": "res-2", "name": "Resp", "amount": 1, "cost_per_hour": "80", "assignedTasks": ["Task_Approve"]}
            ],
        }
    )
    report = suggest_experiments(_summary(), scenario)
    exp = report.experiments[0]
    # ops pool = 2*40 = 80 of (80 + 80) total -> 0.5 share, +1 on 2 -> 0.25
    assert exp.estimate.cost_pct == round(0.5 * 0.5, 4)


def _rich_summary(**kwargs):
    summary = _summary(**kwargs)
    summary.update({
        "casesCompleted": 100,
        "cost": {"total": 10_000.0},
        "byResource": [
            {"id": "res-1_1", "pool": "Back office", "utilizationPct": 98},
            {"id": "res-2_1", "pool": "Sportello", "utilizationPct": 30},
            {"id": "res-2_2", "pool": "Sportello", "utilizationPct": 30},
            {"id": "res-2_3", "pool": "Sportello", "utilizationPct": 30},
        ],
    })
    summary["byActivity"][0].update({"count": 100, "processing": {"avg": 600.0}, "avgCost": 40.0})
    return summary


def _with_front_desk(scenario, *, amount=3, cost=30.0):
    scenario["resource_profiles"].append({"id": "pool-desk", "name": "Sportello", "resource_list": [
        {"id": "res-2", "name": "Sportello", "amount": amount, "cost_per_hour": str(cost), "assignedTasks": ["Task_Approve"]},
    ]})
    return scenario


def test_automation_halves_the_work_and_its_cost_share():
    report = suggest_experiments(_rich_summary(), _scenario(amount=2, arrival_mean=400.0))
    auto = next(e for e in report.experiments if e.kind == "automate")
    assert auto.share == 0.5 and auto.target_el == "Task_Review" and auto.target_name == "Verifica"
    assert auto.from_amount == auto.to_amount == 2
    # Lavorazione: 600 s per caso su 6000 = 10%, meta' tolta = 5%; in piu' la coda che si accorcia.
    assert auto.estimate.cycle_pct < -0.05
    # Costo dell'attivita': 40 * 100 su 10.000 = 40%, meta' = 20% in meno.
    assert auto.estimate.cost_pct == -0.2


def test_reallocation_moves_one_unit_from_the_least_loaded_pool():
    report = suggest_experiments(_rich_summary(), _with_front_desk(_scenario(amount=1, cost=40.0)))
    move = next(e for e in report.experiments if e.kind == "reallocate")
    assert (move.pool_id, move.from_amount, move.to_amount) == ("pool-ops", 1, 2)
    assert (move.donor_pool_id, move.donor_pool_name, move.donor_from_amount) == ("pool-desk", "Sportello", 3)
    add = next(e for e in report.experiments if e.kind == "add_resource")
    assert move.estimate.cycle_pct == add.estimate.cycle_pct
    # Costo orario: 40 + 90 = 130; chi arriva costa 40, chi parte 30: +10 / 130.
    assert move.estimate.cost_pct == round(10 / 130, 4)
    assert "45%" in move.rationale


def test_no_reallocation_when_the_donor_would_become_the_bottleneck():
    summary = _rich_summary()
    for row in summary["byResource"][1:]:
        row["utilizationPct"] = 70  # 3 al 70% -> 2 al 105%
    report = suggest_experiments(summary, _with_front_desk(_scenario(amount=1)))
    assert "reallocate" not in [e.kind for e in report.experiments]


def test_no_reallocation_from_a_single_resource():
    report = suggest_experiments(_rich_summary(), _with_front_desk(_scenario(amount=1), amount=1))
    assert "reallocate" not in [e.kind for e in report.experiments]

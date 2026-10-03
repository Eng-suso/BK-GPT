"""Il giudice L2 calibrato contro un umano: le domande di discovery necessarie.

Prima di usare il giudice sul lavoro dell'agente bisogna sapere quanto gli si
puo' credere. Qui risponde alla stessa domanda chiusa a cui ha gia' risposto un
umano - "questa domanda di discovery e' necessaria, o le fonti la chiudono
gia'?" - su 18 domande dei due casi del golden set, con le interviste come
materiale. Si misurano accuracy e kappa.

Gira sul modello dei test e solo con l'opt-in:

    DELIR_AGENT_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l2_semantic/test_judge_calibration.py -q -s

Finche' le etichette sono `draft_da_validare` il risultato si riporta e non fa
fallire niente: un giudice tarato su etichette non firmate imparerebbe le
opinioni di chi le ha scritte.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.evals.judge import agreement, judge_bounded
from tests.live_llm import skip_unless_live

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parents[1] / "golden"
DATASET = HERE / "calibration_discovery.json"
REPORT = GOLDEN / "reports" / "judge_calibration.json"

# Sotto questo kappa il giudice non distingue abbastanza dal caso per fare da
# metro: 0.6 e' la soglia usuale di un accordo "sostanziale".
MIN_KAPPA = 0.6

pytestmark = [pytest.mark.live_llm, pytest.mark.agent_eval]

if os.environ.get("DELIR_AGENT_EVAL") != "1":
    pytest.skip("eval del giudice spento: esporta DELIR_AGENT_EVAL=1", allow_module_level=True)
skip_unless_live()


def _sources(case: str) -> str:
    return "\n\n".join(
        f"--- {path.name}\n{path.read_text(encoding='utf-8')}"
        for path in sorted((GOLDEN / case / "sources").glob("*.md"))
    )


def test_the_judge_agrees_with_a_human_on_necessary_discovery_questions():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    sources = {case: _sources(case) for case in {item["case"] for item in data["items"]}}

    rows = []
    for item in data["items"]:
        verdict = judge_bounded(question=data["question"], context=sources[item["case"]], item=item["question"])
        rows.append(
            {
                "question": item["question"],
                "human": item["necessary"],
                "judge": verdict.yes,
                "confidence": verdict.confidence,
                "reason": verdict.reason,
            }
        )

    scores = agreement([row["judge"] for row in rows], [row["human"] for row in rows])
    report = {
        "status": data["status"],
        **scores,
        "disagreements": [row for row in rows if row["judge"] != row["human"]],
        "rows": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "accuracy", "kappa")}, ensure_ascii=False))

    if data["status"] != "validated":
        pytest.skip(f"etichette non ancora validate: kappa {scores['kappa']} misurato, non usato come gate")
    assert scores["kappa"] >= MIN_KAPPA, f"giudice non calibrato: kappa {scores['kappa']} < {MIN_KAPPA}"

"""G3, diagnosi: uno scenario SIMOD con i cicli senza uscita riaperti.

    uv run python tests/simulation/benchmark/g3/fix_dead_loops.py AcademicCredentials_diff

SIMOD 5.2.1 puo' dare probabilita' 0 all'uscita di un ciclo quando nel train
l'attivita' del ciclo e' rara: ogni caso che ci entra ripete fino al tetto del
motore. Questo script trova i gateway che dopo un'attivita' tornano indietro con
probabilita' 1 e lasciano l'uscita a 0, e mette all'uscita la frequenza vista nel
train (casi con l'attivita' / esecuzioni dell'attivita'). Scrive lo scenario in
``discovered/<log>_<variante>-loopfix/``, solo se c'e' qualcosa da riaprire.

Non e' una correzione di prodotto: serve a separare, nella decisione G3, quanto
pesa questo difetto da quanto vale il resto del modello scoperto.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark.eval_harness import INPUTS
from tests.simulation.benchmark.log_distance import read_csv_log

HERE = Path(__file__).resolve().parent
BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _graph(bpmn: Path) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    root = ET.parse(bpmn).getroot()
    flows = {f.get("id"): (f.get("sourceRef"), f.get("targetRef")) for f in root.iter(f"{BPMN}sequenceFlow")}
    names = {t.get("id"): t.get("name") for t in root.iter(f"{BPMN}task")}
    return flows, names


def _reaches(flows: dict[str, tuple[str, str]], start: str, goal: str) -> bool:
    seen, todo = set(), [start]
    while todo:
        node = todo.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            todo.extend(target for source, target in flows.values() if source == node)
    return False


def fix(folder: Path) -> list[dict]:
    log = folder.name.rsplit("_", 1)[0]
    flows, names = _graph(folder / f"{log}.bpmn")
    scenario = json.loads((folder / f"{log}.json").read_text(encoding="utf-8"))
    train = read_csv_log(INPUTS / "real-life" / f"{log}_train.csv.gz")
    executions = Counter(e.activity for e in train)
    cases_with = Counter(activity for _, activity in {(e.case_id, e.activity) for e in train})

    fixed = copy.deepcopy(scenario)
    changes = []
    for gateway in fixed["gateway_branching_probabilities"]:
        gid = gateway["gateway_id"]
        before = [source for source, target in flows.values() if target == gid and source in names]
        loop = [p for p in gateway["probabilities"] if p["value"] >= 1.0 and _reaches(flows, flows[p["path_id"]][1], gid)]
        exits = [p for p in gateway["probabilities"] if p["value"] == 0.0]
        if len(before) != 1 or len(loop) != 1 or len(exits) != 1:
            continue
        activity = names[before[0]]
        exit_probability = cases_with[activity] / executions[activity]
        exits[0]["value"] = exit_probability
        loop[0]["value"] = 1.0 - exit_probability
        changes.append({"gateway": gid, "after": activity, "exit_probability": exit_probability,
                        "train_cases": cases_with[activity], "train_executions": executions[activity]})

    if not changes:
        return changes
    out = folder.with_name(f"{folder.name}-loopfix")
    out.mkdir(exist_ok=True)
    (out / f"{log}.bpmn").write_bytes((folder / f"{log}.bpmn").read_bytes())
    (out / f"{log}.json").write_text(json.dumps(fixed, indent=2) + "\n", encoding="utf-8")
    discovery = json.loads((folder / "discovery.json").read_text(encoding="utf-8"))
    discovery["diagnostic"] = {"from": folder.name, "dead_loops_reopened": changes}
    (out / "discovery.json").write_text(json.dumps(discovery, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", help="cartella in discovered/, es. AcademicCredentials_diff")
    args = parser.parse_args(argv)
    changes = fix(HERE / "discovered" / args.scenario)
    print(json.dumps(changes, indent=2, ensure_ascii=False))
    return 0 if changes else 1


if __name__ == "__main__":
    raise SystemExit(main())

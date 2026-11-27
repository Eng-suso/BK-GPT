"""B3.2: la sola fase dei ritardi estranei di SIMOD 5.2.1 sopra uno scenario dato.

Gira nel venv di ricerca di SIMOD e non importa nulla di DeliR:

    python simod_delays.py --config simod_extr.yml --bpmn M.bpmn --json S.json --out DIR [--seed S]

``--config`` e' la configurazione di G3b (``g3b/configs/simod_extr.yml``) con il log gia'
riempito: da li' vengono gli identificativi delle colonne, il preprocessing e i parametri
dei ritardi (eclipse-aware, ``relative_emd``, 20 iterazioni, 3 simulazioni per iterazione),
gli stessi di "SIMOD con ritardi estranei". Il log si legge come lo legge la CLI di SIMOD
(``EventLog.from_path``), poi si chiama ``ExtraneousDelaysOptimizer`` (la classe che SIMOD
usa nella sua pipeline) con un modello che e' lo scenario dato cosi' com'e': BPMN, risorse,
calendari, durate, probabilita' e arrivi restano fissati. Alla fine i timer si aggiungono
al BPMN con ``add_timers_to_bpmn_model`` e allo scenario come ``event_distribution``, come
fa SIMOD nel modello finale.

Diversamente dalla pipeline di SIMOD la ricerca e' ripetibile: ``--seed`` va a ``random``,
``numpy`` (le simulazioni di Prosimos dentro la ricerca) e ``HYPEROPT_FMIN_SEED`` (hyperopt).

Scrive ``DIR/model.bpmn``, ``DIR/scenario.json`` e ``DIR/delays.json`` (attivita', media in
secondi). Uscita 4 se supera ``--discovery-seconds`` (budget del §6).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path

import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "g3b" / "tools"))
from prosimos_sim import budget  # noqa: E402  (stesso budget su thread degli strumenti di G3b)


class FixedModel:
    """Quello che ``ExtraneousDelaysOptimizer`` legge di un ``BPSModel``: il BPMN e lo scenario."""

    def __init__(self, bpmn: Path, scenario: dict):
        self.process_model = bpmn
        self._scenario = scenario

    def to_prosimos_format(self) -> dict:
        return json.loads(json.dumps(self._scenario))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bpmn", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("--discovery-seconds", type=int, default=7200)
    args = parser.parse_args()

    os.environ["HYPEROPT_FMIN_SEED"] = str(args.seed)
    random.seed(args.seed)
    numpy.random.seed(args.seed)

    from simod.event_log.event_log import EventLog
    from simod.extraneous_delays.optimizer import ExtraneousDelaysOptimizer
    from simod.extraneous_delays.utilities import add_timers_to_bpmn_model
    from simod.settings.simod_settings import SimodSettings

    settings = SimodSettings.from_path(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    bpmn = args.out / "model.bpmn"
    shutil.copy(args.bpmn, bpmn)
    scenario = json.loads(args.json.read_text(encoding="utf-8"))
    with budget(args.discovery_seconds, "la discovery dei ritardi"):
        event_log = EventLog.from_path(
            log_ids=settings.common.log_ids,
            train_log_path=settings.common.train_log_path,
            preprocessing_settings=settings.preprocessing,
            need_test_partition=False,
        )
        work = args.out / "work"
        work.mkdir(exist_ok=True)
        optimizer = ExtraneousDelaysOptimizer(event_log, FixedModel(args.bpmn, scenario), settings.extraneous_activity_delays, work)
        delays = optimizer.run()
        shutil.rmtree(work, ignore_errors=True)
    add_timers_to_bpmn_model(bpmn, delays)
    scenario["event_distribution"] = [delay.to_dict() for delay in delays]
    (args.out / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (args.out / "delays.json").write_text(
        json.dumps({d.activity_name: round(float(d.duration_distribution.mean), 1) for d in delays}, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

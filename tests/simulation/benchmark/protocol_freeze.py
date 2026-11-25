"""PROTO-01: congela per hash i log holdout, una volta sola, prima di qualsiasi misura.

    uv run python scripts/fetch_datasets.py fetch camargo-2022-reproducibility bpic2015-municipality1 bpic2011-hospital
    uv run python tests/simulation/benchmark/protocol_freeze.py

Scrive ``protocol/holdout.lock.json``: per ogni log holdout i file, il loro SHA-256
e la dimensione, la categoria, l'organizzazione e perche' e' indipendente dai log
di sviluppo. Legge i file solo per l'impronta. Se il lucchetto esiste non lo
riscrive: cambiare gli holdout e' una decisione di Sohayb, scritta in LOG.md, e
richiede ``--refreeze``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import fetch_datasets
from tests.simulation.benchmark.protocol import COMPLETE, LOCK_PATH, PARTIAL, SYNTHETIC

FROZEN_ON = "2026-11-25"
_CAMARGO = "camargo-2022-reproducibility"
_LOGS = "reproducibility_package_caise_22/event_logs"

# La scelta, scritta prima di aprire qualsiasi log (criteri in PROTOCOL.md §3).
HOLDOUTS = (
    {
        "id": "production",
        "title": "Production (fabbricazione di parti su commessa)",
        "category": COMPLETE,
        "dataset": _CAMARGO,
        "organization": "azienda manifatturiera (Levy, 2014), via Camargo et al. 2022",
        "independent_because": "nessuna organizzazione o processo dei log di sviluppo; mai letto da DeliR",
        "split": "test pubblicato dal pacchetto (tst_Production.csv); train = log meno i casi di test",
        "names": ["Production", "tst_Production"],
        "files": [f"{_LOGS}/public_real_logs/Production.zip", f"{_LOGS}/test_partitions/tst_Production.csv"],
    },
    {
        "id": "consulta_data_mining",
        "title": "ConsultaDataMining 2016-2018 (richieste accademiche)",
        "category": COMPLETE,
        "dataset": _CAMARGO,
        "organization": "universita' colombiana, via Camargo et al. 2022",
        "independent_because": (
            "processo diverso da ogni log di sviluppo e mai letto da DeliR; l'organizzazione potrebbe essere "
            "la stessa di AcademicCredentials: indipendenza di processo, non garantita di organizzazione"
        ),
        "split": "test pubblicato dal pacchetto (tst_ConsultaDataMining201618.csv)",
        "names": ["ConsultaDataMining201618", "tst_ConsultaDataMining201618"],
        "files": [
            f"{_LOGS}/public_real_logs/ConsultaDataMining201618.zip",
            f"{_LOGS}/test_partitions/tst_ConsultaDataMining201618.csv",
        ],
    },
    {
        "id": "purchasing_example",
        "title": "PurchasingExample (acquisti, log simulato senza modello pubblicato)",
        "category": COMPLETE,
        "dataset": _CAMARGO,
        "organization": "esempio sintetico di acquisti, via Camargo et al. 2022",
        "independent_because": (
            "modello diverso da Procure_to_Pay e dagli altri sintetici; il modello che l'ha generato non e' "
            "pubblicato, quindi conta come log a osservabilita' completa senza verita' nota"
        ),
        "split": "test pubblicato dal pacchetto (tst_PurchasingExample.csv)",
        "names": ["PurchasingExample", "tst_PurchasingExample"],
        "files": [f"{_LOGS}/syntetic_logs/PurchasingExample.zip", f"{_LOGS}/test_partitions/tst_PurchasingExample.csv"],
    },
    {
        "id": "confidential_2000",
        "title": "Confidential 2000 casi (sintetico con il modello di simulazione pubblicato)",
        "category": SYNTHETIC,
        "dataset": _CAMARGO,
        "organization": "modello di processo riservato, via Camargo et al. 2022",
        "independent_because": (
            "modello diverso da tutti i sintetici di sviluppo; la verita' e' ConfidentialProcessModel.bpmn. "
            "La variante da 1000 casi viene dallo stesso modello: e' chiusa con lui, non e' un log di sviluppo"
        ),
        "split": "test pubblicato dal pacchetto (tst_confidential_2000.csv)",
        "names": ["confidential_2000", "tst_confidential_2000", "confidential_1000", "tst_confidential_1000", "ConfidentialProcessModel"],
        "files": [
            f"{_LOGS}/syntetic_logs/confidential_2000.zip",
            f"{_LOGS}/test_partitions/tst_confidential_2000.csv",
            f"{_LOGS}/syntetic_logs/confidential_1000.zip",
            f"{_LOGS}/test_partitions/tst_confidential_1000.csv",
            f"{_LOGS}/syntetic_logs/simulation_models/ConfidentialProcessModel.bpmn",
        ],
    },
    {
        "id": "bpic2015_municipality1",
        "title": "BPI Challenge 2015, Municipality 1 (permessi edilizi)",
        "category": PARTIAL,
        "dataset": "bpic2015-municipality1",
        "organization": "comune olandese",
        "independent_because": "nessuna organizzazione o processo dei log di sviluppo; mai letto da DeliR",
        "split": "meta' dei casi per inizio",
        "names": ["BPIC15_1"],
        "files": ["BPIC15_1.xes"],
    },
    {
        "id": "bpic2011_hospital",
        "title": "BPI Challenge 2011, Hospital log (ginecologia di un ospedale universitario)",
        "category": PARTIAL,
        "dataset": "bpic2011-hospital",
        "organization": "ospedale universitario olandese",
        "independent_because": "nessuna organizzazione o processo dei log di sviluppo; mai letto da DeliR",
        "split": "meta' dei casi per inizio",
        "names": ["Hospital_log"],
        "files": ["Hospital_log.xes.gz"],
    },
)

# Archivi che contengono log holdout: chiusi anche loro (e con loro le copie dei log
# di sviluppo che ci stanno dentro, che non servono: i log di sviluppo si leggono da
# datasets/ o dal loro dataset del manifest).
CONTAINERS = (
    {
        "dataset": _CAMARGO,
        "file": "reproducibility_package.zip",
        "why": "contiene Production, ConsultaDataMining, PurchasingExample e confidential",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(cache_root: Path) -> dict:
    manifest = fetch_datasets.load_manifest()
    holdouts = []
    for spec in HOLDOUTS:
        dataset = str(spec["dataset"])
        entry = manifest[dataset]
        files = []
        for relative in spec["files"]:
            path = cache_root / dataset / relative
            if not path.is_file():
                raise SystemExit(f"manca {path}: scaricalo con scripts/fetch_datasets.py fetch {dataset}")
            files.append({"path": relative, "sha256": _sha256(path), "bytes": path.stat().st_size})
        holdouts.append(
            {
                **{k: v for k, v in spec.items() if k != "files"},
                "license": entry["license"],
                "source": entry["source"],
                "files": files,
            }
        )
    return {
        "protocol": "PROTO-01, docs/vpt/PROTOCOL.md",
        "frozen_on": FROZEN_ON,
        "rule": (
            "Questi log non si leggono per sviluppare, scegliere modelli, iperparametri o componenti. "
            "Si aprono una volta, in protocol.final_evaluation(), a selezione congelata."
        ),
        "holdouts": holdouts,
        "containers": list(CONTAINERS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refreeze", action="store_true", help="riscrive un lucchetto esistente (decisione di Sohayb)")
    args = parser.parse_args(argv)
    if LOCK_PATH.exists() and not args.refreeze:
        print(f"{LOCK_PATH} esiste gia': gli holdout sono congelati", file=sys.stderr)
        return 1
    lock = build(fetch_datasets.cache_dir())
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scritto {LOCK_PATH}, SHA-256 {hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

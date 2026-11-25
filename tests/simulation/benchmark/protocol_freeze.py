"""PROTO-01 e PROTO-02: congela per hash i log holdout, una volta sola, prima di qualsiasi misura.

    uv run python scripts/fetch_datasets.py fetch camargo-2022-reproducibility bpic2015-municipality1 bpic2011-hospital
    uv run python tests/simulation/benchmark/protocol_freeze.py              # primo set (PROTO-01)
    uv run python scripts/fetch_datasets.py fetch bps-quality-framework road-traffic-fines das-rp
    uv run python tests/simulation/benchmark/protocol_freeze.py --set 2      # secondo set (PROTO-02)

Scrive ``protocol/holdout.lock.json``: per ogni log holdout i file, il loro SHA-256
e la dimensione, la categoria, l'organizzazione e perche' e' indipendente dai log
di sviluppo. Legge i file solo per l'impronta. Se il lucchetto esiste non lo
riscrive: cambiare gli holdout e' una decisione di Sohayb, scritta in LOG.md, e
richiede ``--refreeze``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import fetch_datasets
from tests.simulation.benchmark.protocol import (
    COMPLETE,
    LOCK2_PATH,
    LOCK_PATH,
    PARTIAL,
    SYNTHETIC,
    lock_digest,
    sha256_of,
)

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


FROZEN_ON_2 = "2026-11-25"
_BPSQF = "bps-quality-framework"

# Il secondo set (PROTO-02), scelto dopo l'inventario del radar (RAD-01) e prima di ogni uso.
# Criteri in PROTOCOL.md §10: indipendente dai log di sviluppo, dal primo set e dagli altri log
# del radar dichiarati di sviluppo; licenza che permette di usarne i numeri.
HOLDOUTS_2 = (
    {
        "id": "callcenter",
        "title": "CallCenter (contatti di un call center, una settimana del 2008)",
        "category": COMPLETE,
        "dataset": _BPSQF,
        "closes_dataset": False,
        "organization": "call center (origine non documentata nel pacchetto BPS Quality Framework)",
        "sector": "assistenza clienti",
        "independent_because": (
            "nessun log di sviluppo o holdout e' un call center; nessuna copia nelle altre voci del radar "
            "(RAD-01, per impronta, nome e contenuto). Il resto del pacchetto resta di sviluppo"
        ),
        "split": "train / test pubblicati dal pacchetto (una settimana ciascuno)",
        "names": ["CallCenter"],
        "files": [
            "CallCenter_train.csv.gz",
            "CallCenter_test.csv.gz",
            # modelli e misure ricavati dal log: chiusi con lui (i simulati CallCenter_* li chiude il nome)
            "real-life/CallCenter_SIMOD.bpmn",
            "real-life/CallCenter_SIMOD_parameters.json",
            "real-life/CallCenter_SIMOD.csv",
            "real-life/CallCenter_ServiceMiner.csv",
        ],
    },
    {
        "id": "road_traffic_fines",
        "title": "Road Traffic Fine Management (multe stradali, 2000-2013)",
        "category": PARTIAL,
        "dataset": "road-traffic-fines",
        "organization": "polizia locale italiana",
        "sector": "pubblica amministrazione",
        "independent_because": (
            "nessun log di sviluppo o holdout viene da questa organizzazione o da una polizia; l'altro log "
            "della PA nel radar (BPIC 2018) e' un'agenzia tedesca e resta di sviluppo"
        ),
        "split": "meta' dei casi per inizio",
        "names": ["Road_Traffic_Fine_Management_Process", "Trafic"],
        "files": ["Road_Traffic_Fine_Management_Process.xes.gz"],
    },
    {
        "id": "road_traffic_fines_das",
        "title": "Road Traffic Fines, estratto CSV del pacchetto DAS-RP",
        "category": PARTIAL,
        "dataset": "das-rp",
        "closes_dataset": False,
        "organization": "polizia locale italiana (stessi casi del log 4TU, RAD-01)",
        "sector": "pubblica amministrazione",
        "independent_because": "e' una copia dell'holdout road_traffic_fines: chiusa con lui",
        "split": "come road_traffic_fines",
        "names": ["Trafic"],
        "files": ["assets/Trafic/Trafic.zip"],
    },
)
CONTAINERS_2 = tuple(
    {"dataset": _BPSQF, "file": name, "why": "contiene i file di CallCenter (log, simulati, modelli o misure)"}
    for name in ("original-event-logs.zip", "simulated-logs.zip", "BPS-models.zip", "measures.zip")
)


def build(cache_root: Path, specs: tuple[dict, ...] = HOLDOUTS, containers: tuple[dict, ...] = CONTAINERS,
          frozen_on: str = FROZEN_ON, protocol_name: str = "PROTO-01, docs/vpt/PROTOCOL.md") -> dict:
    manifest = fetch_datasets.load_manifest()
    holdouts = []
    for spec in specs:
        dataset = str(spec["dataset"])
        entry = manifest[dataset]
        files = []
        for relative in spec["files"]:
            path = cache_root / dataset / relative
            if not path.is_file():
                raise SystemExit(f"manca {path}: scaricalo con scripts/fetch_datasets.py fetch {dataset}")
            files.append({"path": relative, "sha256": sha256_of(path), "bytes": path.stat().st_size})
        holdouts.append(
            {
                **{k: v for k, v in spec.items() if k != "files"},
                "license": entry["license"],
                "source": entry["source"],
                "files": files,
            }
        )
    return {
        "protocol": protocol_name,
        "frozen_on": frozen_on,
        "rule": (
            "Questi log non si leggono per sviluppare, scegliere modelli, iperparametri o componenti. "
            "Si aprono una volta, in protocol.final_evaluation(), a selezione congelata."
        ),
        "holdouts": holdouts,
        "containers": list(containers),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refreeze", action="store_true", help="riscrive un lucchetto esistente (decisione di Sohayb)")
    parser.add_argument("--set", type=int, choices=(1, 2), default=1, help="1 = PROTO-01, 2 = secondo set di PROTO-02")
    args = parser.parse_args(argv)
    path = LOCK_PATH if args.set == 1 else LOCK2_PATH
    if path.exists() and not args.refreeze:
        print(f"{path} esiste gia': gli holdout sono congelati", file=sys.stderr)
        return 1
    if args.set == 1:
        lock = build(fetch_datasets.cache_dir())
    else:
        lock = build(fetch_datasets.cache_dir(), HOLDOUTS_2, CONTAINERS_2, FROZEN_ON_2, "PROTO-02, docs/vpt/PROTOCOL.md §10")
        lock["independent_of"] = f"primo set, lucchetto {lock_digest(LOCK_PATH)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scritto {path}, SHA-256 {lock_digest(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

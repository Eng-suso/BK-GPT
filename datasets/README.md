# Dataset di DeliR

Tutti i dataset per test, benchmark e ricerca. Il catalogo macchina è
[`manifest.json`](./manifest.json); questo file lo spiega. Prima di usare un
dataset leggi la sua licenza: il repo è **pubblico**.

## Come si usano

```bash
uv run python scripts/fetch_datasets.py list                       # catalogo
uv run python scripts/fetch_datasets.py verify                     # i dataset nel repo ci sono
uv run python scripts/fetch_datasets.py fetch --all                # tutti quelli scaricabili
uv run python scripts/fetch_datasets.py fetch --all --allow-noncommercial   # anche quelli accademici
uv run python scripts/fetch_datasets.py fetch --collection radar   # Research Radar (~3 GB)
uv run python scripts/fetch_datasets.py path bpic2012              # dove sta
```

I file scaricati vanno in `~/.cache/delir-datasets/<id>/` (o in
`DELIR_DATASETS_CACHE`) e si accettano solo se l'MD5 coincide con il manifest. I
repository git si fermano sul commit fissato. In una sessione cloud servono gli
host `zenodo.org` e `data.4tu.nl` (ambiente **BK-GPT**); GitHub passa dal proxy git.

## Catalogo

| Id | Dove | Licenza | A cosa serve |
| --- | --- | --- | --- |
| `extraneous-delays-inputs` | nel repo, `extraneous-delays/inputs` | CC BY 4.0 | 4 processi sintetici con 0, 1, 3, 5 timer (verità nota) e 3 log reali con split train/test e scenari SIMOD. B1, B2, B3, B5 |
| `extraneous-delays-paper-metrics` | nel repo, `extraneous-delays/paper-results` | CC BY 4.0 | metriche pubblicate dal paper: la baseline da battere. B2, B5 |
| `simod-samples` | nel repo, `simod/` | Apache-2.0 | configurazioni SIMOD e log Insurance Claims con ritardi noti. Spike G3, B5 |
| `extraneous-delays-outputs` | cache, 99,6 MB | CC BY 4.0 | tutti i log simulati del paper, per confronti distribuzione per distribuzione |
| `camargo-2022-reproducibility` | cache, 282,8 MB | CC BY 4.0 | log completi e divisi, modelli, risultati di Camargo et al.: validazione predittiva (H1) |
| `bpic2012` | cache, 3,3 MB | 4TU General Terms of Use | prestiti, circa 13.087 casi e 262.200 eventi: benchmark A → B (SIM-36) |
| `bpic2013-incidents` | cache, 1,3 MB | 4TU General Terms of Use | incidenti Volvo IT: benchmark A → B |
| `prosimos` | cache (git) | **nessuna licenza** nel repo upstream | test e scenari del motore, `input_output_files.zip` degli esperimenti BPM 2022: compatibilità dell'integrazione |
| `simod` | cache (git) | Apache-2.0 | repository completo SIMOD: baseline di H1 |
| `bpic2020` | cache, 5 log, 5,5 MB | CC BY-NC 4.0 | note spese di viaggio: **solo ricerca accademica**, mai nei numeri commerciali |

## Research Radar

33 voci in più (21 dataset, 12 repository di ricerca) con `"collection": "radar"`: log
cross-industry (BPIC 2017 completo, 2018, 2019, Sepsis, Hospital Billing, Road Traffic
Fines, Helpdesk), OCEL 2.0, drift con verità nota, dati controfattuali (SimBank, ProCause),
il BPS Quality Framework e i repository di AT-KDE, Kronos, AgentSimulator, ProSiT, DAS,
POWL, SimOC, SimPy, salabim, QueueSim. `fetch --all` non li scarica. Elenco, a cosa serve
ognuno e regole d'uso in [`../docs/vpt/RESEARCH_RADAR.md`](../docs/vpt/RESEARCH_RADAR.md).
Il radar non è sviluppo né holdout finché `docs/vpt/PROTOCOL.md` (PROTO-02) non lo dichiara.

## Regole

- Nel repo entrano solo dati con licenza che ne permette la ripubblicazione (oggi
  CC BY 4.0 e Apache-2.0), con un `ATTRIBUTION.md` accanto. Il test
  `tests/simulation/test_dataset_manifest.py` lo verifica in CI.
- Un dataset `academic` (non commerciale) si scarica solo con
  `--allow-noncommercial` e i suoi numeri non entrano in materiali di vendita.
- Nessun dato di clienti, anche anonimizzato, entra in `datasets/`.
- Un nuovo dataset si aggiunge al manifest con URL, MD5 (o commit), dimensione,
  licenza e il blocco del piano che lo usa.
- Per la ricerca si usano tutti i dataset (decisione di Sohayb del 2026-11-25: il prodotto non
  è ancora in vendita); la licenza resta registrata per LIC-01 e per quando si vende.

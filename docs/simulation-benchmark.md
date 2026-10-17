# DeliR Simulation Benchmark (SIM-36)

Il benchmark dice quanto un twin prevede bene un periodo che non ha visto. Il twin
impara dal **periodo A** e prevede il **periodo B**; la previsione si misura contro il
B reale, mai contro A. La prima previsione è il **gemello ingenuo**, "B sarà come A":
è la baseline che ogni twin, SIMOD compreso (gate G3), deve battere.

## Log

| Chiave | Log | Licenza |
|---|---|---|
| `bpic2012` | BPI Challenge 2012, richieste di prestito (DOI `10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f`) | 4TU General Terms of Use |
| `bpic2013_incidents` | BPI Challenge 2013, incidenti Volvo IT (DOI `10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee`) | 4TU General Terms of Use |

Il BPIC 2020 è CC BY-NC: escluso. I file si scaricano una volta in
`~/.cache/delir-benchmark` (o `DELIR_BENCHMARK_CACHE`) e si accettano solo con l'MD5
che 4TU dichiara nei metadati del file. Nessun mirror.

## Metriche

| Metrica | Cosa misura | Tipo |
|---|---|---|
| `cycle_time_distribution` | Wasserstein-1 fra le distribuzioni del cycle time, diviso per la media reale | Fedeltà |
| `waiting_time_distribution` | Lo stesso sull'attesa di ogni esecuzione | Fedeltà |
| `throughput_error` | Errore relativo sui casi completati al giorno | Fedeltà |
| `path_frequency_distance` | Variazione totale fra le frequenze delle varianti (0–1) | Fedeltà |
| `resource_workload_error` | Variazione totale fra le quote di lavoro per risorsa (0–1) | Fedeltà |
| `sla_prediction_error_pp` | Scarto, in punti percentuali, della quota di casi entro l'obiettivo (80° percentile del cycle di A) | Previsione |
| `calibration_seconds` | Dal log importato al twin pronto | Efficienza |
| `simulation_seconds` | Durata dei run del motore | Efficienza |
| `human_configuration_minutes` | Minuti di lavoro del consulente: si cronometra, resta `null` finché nessuno lo fa | Semplicità |

Senza calendari di disponibilità l'utilizzo vero delle risorse non si misura: il
benchmark confronta come si divide il lavoro, non quanto è carica ogni persona.

## Come si lancia

```
uv run python tests/simulation/benchmark/run_baseline.py            # tutti i log
uv run python tests/simulation/benchmark/run_baseline.py bpic2012   # uno solo
```

Il runner scrive `tests/simulation/benchmark/baseline.json`. Un log che 4TU non dà
(manutenzione `503 StorageMaintenance`, rete chiusa) finisce nel file con il motivo e
l'uscita è 1: la baseline non si inventa.

Il codice vive in `tests/simulation/benchmark/`: `benchmark_metrics.py` (metriche su
due `EventLog` canonici), `benchmark_datasets.py` (download verificato e lettura XES),
`run_baseline.py` (runner). I test non usano la rete.

## Stato

- Metriche, download verificato e runner: pronti, testati su log costruiti a mano.
- Baseline misurata: **non ancora**. Nella sessione cloud del 17 ottobre `data.4tu.nl`
  era fuori dalla policy di rete (proxy 403). Da verificare al primo accesso: la forma
  dell'API dei file di 4TU (`/v2/articles/<uuid>/files`, campi `name`, `download_url`,
  `computed_md5`/`supplied_md5`) e i nomi dei file.
- Dopo la baseline: SIM-19, calibrare un twin vero su A e misurarlo su B con queste metriche.

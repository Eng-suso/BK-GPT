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

Il BPIC 2020 è CC BY-NC: escluso. I log si scaricano con `scripts/fetch_datasets.py`
nella sua cache (`~/.cache/delir-datasets`, o `DELIR_DATASETS_CACHE`) e si accettano
solo con l'MD5 di `datasets/manifest.json`. Non entrano nel repo: la licenza 4TU non
ne permette la ripubblicazione. Nel repo stanno solo le metriche.

Lettura: BPIC 2012 ha una riga per transizione (start/complete); BPIC 2013 ha cambi di
stato istantanei, e il sottostato (`In Progress`, `Closed`…) fa parte dell'attività
(`Accepted · In Progress`). Un evento senza inizio è istantaneo.

## Metriche

Le stesse dell'harness di B2 (`tests/simulation/benchmark/log_distance.py`, port di
`log-distance-measures` 2.2), così questa baseline si confronta con quella di B2, con il
paper e con ogni twin futuro. Tempi in ore.

| Metrica | Cosa misura |
|---|---|
| W1 cycle time | Wasserstein-1 fra le durate dei casi |
| NGD | Distanza fra le frequenze dei 3-grammi di attività, da 0 a 1 |
| RED | Inizi e fini rispetto all'inizio del proprio caso |
| AED | Inizi e fini nel tempo assoluto |
| CED | Ora del giorno di inizi e fini, giorno della settimana per giorno |
| CAR | Arrivo dei casi nel tempo assoluto |

## Il gemello ingenuo

Il log si divide a metà dei casi per inizio: A sono i primi, B gli altri. "B = A" è A
spostato in avanti fino a far cadere la mediana degli inizi dei casi di A su quella di
B (la mediana, perché un caso isolato anni prima non sposti tutto il resto). Lo
spostamento è di settimane intere, sull'ora locale del log (Europa centrale): il
gemello ripete arrivi, percorsi, durate e calendario di A, ora legale compresa. Gli
eventi seguono l'inizio del proprio caso in tempo assoluto, quindi le durate sono
quelle vere. Il prezzo delle settimane intere è uno scarto fino a 3,5 giorni fra le
due mediane, che resta in AED e CAR.

Ogni replica estrae con reinserimento tanti casi di A quanti ne ha B, con seed
`20261124 + replica`; 10 repliche e intervallo t al 95%, come B2.

## Come si lancia

```
uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
uv run python tests/simulation/benchmark/run_baseline.py bpic2012
uv run python tests/simulation/benchmark/run_baseline.py bpic2013_incidents
```

Ogni comando scrive `tests/simulation/benchmark/sim36/<log>.json` (identico bit per bit
con lo stesso seed) e ricompone `sim36/baseline.md` da tutti i log della cartella. Un
log che 4TU non dà (manutenzione `503 StorageMaintenance`, rete chiusa) finisce nel
file con il motivo e l'uscita è 1: la baseline non si inventa. I test
(`test_run_baseline.py`, `test_benchmark_datasets.py`) non usano la rete.

## Baseline (2026-11-24, seed 20261124, 10 repliche)

Tempi in ore, media ± semiampiezza dell'intervallo al 95%. File: `tests/simulation/benchmark/sim36/`.

| Log | Casi A / B | W1 cycle time | NGD | RED | AED | CED | CAR |
|---|---|---|---|---|---|---|---|
| BPIC 2012 | 6.543 / 6.544 | 16,931 ± 1,518 | 0,055 ± 0,002 | 16,554 ± 1,567 | 60,281 ± 3,275 | 0,222 ± 0,013 | 48,697 ± 2,653 |
| BPIC 2013 incidents | 3.776 / 3.778 | 383,995 ± 7,811 | 0,329 ± 0,004 | 176,788 ± 3,981 | 334,396 ± 16,091 | 1,751 ± 0,079 | 290,944 ± 6,383 |

Come si legge:

- **BPIC 2012**: A (ottobre-metà dicembre 2011) e B (metà dicembre 2011-febbraio 2012)
  hanno lo stesso processo (NGD 0,055). "B = A" sbaglia la durata dei casi di circa
  17 ore e gli arrivi di circa due giorni (CAR 49 ore). Delle 262.200 righe, 26.318
  `SCHEDULE` non sono né inizio né fine e restano fuori (`rows_excluded` nel JSON).
- **BPIC 2013 incidents**: B copre solo 4 giorni (2-6 maggio 2012), mentre l'1% dei casi
  di A parte fra marzo 2010 e ottobre 2011, una coda dell'estrazione del log. "B = A"
  ripete anche quella coda: è quasi tutto l'errore di AED e CAR (circa due settimane).
  W1 è alto (16 giorni) perché i casi vecchi di A sono lunghi e in B non ce ne sono.

## Dopo la baseline

SIM-19 e B3: calibrare un twin vero su A e misurarlo su B con questo comando e queste
metriche; il twin deve battere "B = A" con intervalli che non si sovrappongono.

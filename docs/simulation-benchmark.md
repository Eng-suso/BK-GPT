# DeliR Simulation Benchmark (SIM-36, SIM-36b)

Il benchmark dice quanto un twin prevede bene un periodo che non ha visto. Il twin
impara dal **periodo A** e prevede il **periodo B**; la previsione si misura contro il
B reale, mai contro A. La prima previsione è il **gemello ingenuo**, "B sarà come A":
è la baseline che ogni twin, SIMOD compreso (gate G3), deve battere.

## Log

Il banco principale A → B sono i **3 log reali del paper** *Extraneous Activity
Delays* con il loro train e test (SIM-36b, decisione di Sohayb del 2026-11-24): A è il
train, B il test, gli stessi file con cui B2 misura lo scenario SIMOD del paper. Stanno
nel repo (CC BY 4.0, `datasets/extraneous-delays/inputs/real-life`), niente rete.

| Chiave | Log | Licenza |
|---|---|---|
| `AcademicCredentials` | Credenziali accademiche, train / test del paper (DOI `10.5281/zenodo.10435849`) | CC BY 4.0 |
| `BPIC_2012_W` | BPIC 2012, solo attività `W_`, train / test del paper | CC BY 4.0 |
| `BPIC_2017_W` | BPIC 2017, solo attività `W_`, train / test del paper | CC BY 4.0 |
| `bpic2012` | BPI Challenge 2012, richieste di prestito (DOI `10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f`) | 4TU General Terms of Use |
| `bpic2013_incidents` | BPI Challenge 2013, incidenti Volvo IT (DOI `10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee`), **non adatto al confronto A → B** | 4TU General Terms of Use |

**BPIC 2013 incidents non serve a giudicare un twin.** È una foto degli incidenti
aperti a maggio 2012, non un flusso: con ogni taglio il 100% dei casi di B è troncato
dalla fine del log. La sua baseline resta misurata, ma il JSON
(`unsuitable_for_a_to_b`) e la tabella lo marcano, e nessuna meta lo usa.

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

Sui log train/test A è il train e B il test. Sui log BPIC il log si divide a metà dei
casi per inizio: A sono i primi, B gli altri. "B = A" è A
spostato in avanti fino a far cadere la mediana degli inizi dei casi di A su quella di
B (la mediana, perché un caso isolato anni prima non sposti tutto il resto). Lo
spostamento è di settimane intere, sull'ora locale del log (Europa centrale per i
BPIC; per i CSV del paper, che non hanno fuso, l'orologio scritto nel log): il
gemello ripete arrivi, percorsi, durate e calendario di A, ora legale compresa. Gli
eventi seguono l'inizio del proprio caso in tempo assoluto, quindi le durate sono
quelle vere. Il prezzo delle settimane intere è uno scarto fino a 3,5 giorni fra le
due mediane, che resta in AED e CAR.

Ogni replica estrae con reinserimento tanti casi di A quanti ne ha B, con seed
`20261124 + replica`; 10 repliche e intervallo t al 95%, come B2.

## Come si lancia

```
uv run python tests/simulation/benchmark/run_baseline.py AcademicCredentials BPIC_2012_W BPIC_2017_W   # ~11 s, senza rete
uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
uv run python tests/simulation/benchmark/run_baseline.py bpic2012 bpic2013_incidents
```

Senza argomenti misura tutti i log. Ogni comando scrive
`tests/simulation/benchmark/sim36/<log>.json` (identico bit per bit con lo stesso seed)
e ricompone `sim36/baseline.md` da tutti i log della cartella, con il confronto fra
"B = A" e lo scenario SIMOD di B2 (`b2/baseline.json`) se seed e repliche coincidono. Un
log che 4TU non dà (manutenzione `503 StorageMaintenance`, rete chiusa) finisce nel
file con il motivo e l'uscita è 1: la baseline non si inventa. I test
(`test_run_baseline.py`, `test_benchmark_datasets.py`) non usano la rete.

## Baseline sui log train/test (SIM-36b, 2026-11-24, seed 20261124, 10 repliche)

Tempi in ore, media ± semiampiezza dell'intervallo al 95%. File: `tests/simulation/benchmark/sim36/`.

| Log | Casi A / B | W1 cycle time | NGD | RED | AED | CED | CAR |
|---|---|---|---|---|---|---|---|
| AcademicCredentials | 398 / 398 | 28,827 ± 3,601 | 0,179 ± 0,006 | 25,856 ± 2,223 | 62,309 ± 6,194 | 1,391 ± 0,116 | 95,460 ± 17,106 |
| BPIC 2012 W | 3.030 / 2.976 | 28,061 ± 2,000 | 0,083 ± 0,005 | 10,140 ± 2,565 | 29,710 ± 4,414 | 0,800 ± 0,155 | 38,215 ± 4,309 |
| BPIC 2017 W | 7.402 / 7.376 | 30,602 ± 1,481 | 0,079 ± 0,001 | 11,359 ± 1,570 | 42,785 ± 4,042 | 0,660 ± 0,011 | 35,916 ± 3,821 |

### "B = A" contro lo scenario SIMOD del paper (B2)

Stesso test, stesse metriche, stesso seed e 10 repliche: lo scenario SIMOD del paper
simulato da B2 sullo stack reale. Più basso è meglio; uno dei due vince solo se gli
intervalli al 95% non si sovrappongono.

| Log | W1 cycle time | NGD | RED | AED | CED | CAR |
|---|---|---|---|---|---|---|
| AcademicCredentials | 28,8 contro 174,8 | 0,18 contro 0,76 | 25,9 contro 77,5 | 62,3 contro 121,4 | 1,39 contro 3,33 | 95,5 contro 131,0: pari |
| BPIC 2012 W | 28,1 contro 175,7 | 0,08 contro 0,81 | 10,1 contro 178,5 | 29,7 contro 221,4 | 0,80 contro 1,25 | 38,2 contro 85,8 |
| BPIC 2017 W | 30,6 contro 253,3 | 0,08 contro 0,62 | 11,4 contro 183,5 | 42,8 contro 303,4 | 0,66 contro 0,93 | 35,9 contro 169,6 |

"B = A" vince 17 confronti su 18; pari su CAR di AcademicCredentials (intervalli
larghi: 95,5 ± 17,1 contro 131,0 ± 25,9). Intervalli completi in `sim36/baseline.md`.

Come si legge: il modello SIMOD del paper, simulato così com'è, sbaglia la durata dei
casi di 7-10 giorni; "B = A" di poco più di un giorno. È la soglia di B3: un twin
scoperto dal train deve battere "B = A" su W1, RED e AED con intervalli separati,
su tutti e 3 i log. NGD resta fuori dal criterio: "B = A" ripete tracce reali e parte
avvantaggiato sui percorsi.

## Baseline sui log BPIC divisi a metà (SIM-36, 2026-11-24, seed 20261124, 10 repliche)

| Log | Casi A / B | W1 cycle time | NGD | RED | AED | CED | CAR |
|---|---|---|---|---|---|---|---|
| BPIC 2012 | 6.543 / 6.544 | 16,931 ± 1,518 | 0,055 ± 0,002 | 16,554 ± 1,567 | 60,281 ± 3,275 | 0,222 ± 0,013 | 48,697 ± 2,653 |
| BPIC 2013 incidents (non adatto ad A → B) | 3.776 / 3.778 | 383,995 ± 7,811 | 0,329 ± 0,004 | 176,788 ± 3,981 | 334,396 ± 16,091 | 1,751 ± 0,079 | 290,944 ± 6,383 |

Come si legge:

- **BPIC 2012**: A (ottobre-metà dicembre 2011) e B (metà dicembre 2011-febbraio 2012)
  hanno lo stesso processo (NGD 0,055). "B = A" sbaglia la durata dei casi di circa
  17 ore e gli arrivi di circa due giorni (CAR 49 ore). Delle 262.200 righe, 26.318
  `SCHEDULE` non sono né inizio né fine e restano fuori (`rows_excluded` nel JSON).
- **BPIC 2013 incidents** (non adatto al confronto A → B): B copre solo 4 giorni (2-6 maggio 2012), mentre l'1% dei casi
  di A parte fra marzo 2010 e ottobre 2011, una coda dell'estrazione del log. "B = A"
  ripete anche quella coda: è quasi tutto l'errore di AED e CAR (circa due settimane).
  W1 è alto (16 giorni) per un altro motivo: il log finisce il 22 maggio 2012, quindi i
  casi di B si vedono al massimo per 20 giorni (mediana 95 ore), mentre quelli di A hanno
  avuto tempo di durare (mediana 275 ore). Un twin che non tiene conto di questo taglio
  sbaglia allo stesso modo.

## Dopo la baseline

SIM-19, G3 e B3: calibrare un twin vero sul train e misurarlo sul test con queste
metriche; il twin deve battere "B = A" dei log train/test con intervalli che non si
sovrappongono (meta di B3 in `docs/vpt/PLAN.md`).

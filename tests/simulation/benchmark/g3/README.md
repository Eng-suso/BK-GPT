# G3: spike SIMOD come motore di discovery

Punto G3 di [`docs/vpt/PLAN.md`](../../../../docs/vpt/PLAN.md). SIMOD scopre uno scenario
dai log di train dei 3 log reali; lo scenario si importa in DeliR e si valuta sul log di
test con l'harness di B2, accanto allo scenario SIMOD del paper e al gemello ingenuo.
Risultati in [`results.md`](./results.md) (tabelle) e `results.json` (tutte le repliche).
La decisione è in [`docs/vpt/LOG.md`](../../../../docs/vpt/LOG.md).

## Rifare tutto

```bash
scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"

# 1. Discovery (venv proprio in /var/tmp/delir-vpt-stack/simod-venv, creato la prima volta)
tests/simulation/benchmark/g3/discover.sh all                 # oppure: discover.sh BPIC_2012_W diff

# 2. Diagnosi: riapre i cicli che SIMOD lascia senza uscita (solo AcademicCredentials)
uv run python tests/simulation/benchmark/g3/fix_dead_loops.py AcademicCredentials_diff
uv run python tests/simulation/benchmark/g3/fix_dead_loops.py AcademicCredentials_fuzz

# 3. Valutazione sul percorso del prodotto (import, coda, runner Prosimos 2.1), 10 repliche
uv run python tests/simulation/benchmark/g3/evaluate.py
```

La discovery dipende dall'ottimizzazione di SIMOD (hyperopt, senza seed fissato): rilanciata
dà scenari simili ma non identici. Per questo gli scenari usati sono nel repo, in
`discovered/`; la valutazione su quelli è deterministica (seed 20261124 + replica).

## Cosa c'è

| Percorso | Cosa |
| --- | --- |
| `configs/<log>_{diff,fuzz,extr}.yml` | configurazioni del benchmark di SIMOD (`datasets/simod/config/benchmark`), cambiati solo i percorsi |
| `discover.sh` | installa SIMOD 5.2.1 e lancia la discovery; copia lo scenario migliore in `discovered/` |
| `discovered/<log>_<variante>/` | BPMN e JSON di SIMOD, `discovery.json` (versioni, wall-clock), `simod_runtimes.json` (tempi per fase), `simod_evaluation_metrics.csv` (la valutazione di SIMOD stesso) |
| `discovered/<log>_<variante>-loopfix/` | diagnosi, non uno scenario SIMOD: uscita dal ciclo alla frequenza del train |
| `fix_dead_loops.py` | crea gli scenari di diagnosi |
| `evaluate.py` | harness B2 sugli scenari, confronto con paper e gemello ingenuo |
| `failures/` | tracce degli errori di SIMOD |

Varianti: `diff` calendari fissi per risorsa (CRISP), come lo scenario del paper; `fuzz`
calendari probabilistici (FUZZY, importati grazie a CAL-01); `extr` calendari fissi più
ritardi estranei (eclipse-aware). `fuzz` ed `extr` riusano il BPMN di `diff`, come upstream.

## Ambiente

- SIMOD 5.2.1 (commit `7e5de02`, dalla cache di `scripts/fetch_datasets.py fetch simod`),
  Python 3.12, dipendenze principali prosimos 2.1.0, pix-framework 0.15.0,
  log-distance-measures 2.2.0, extraneous-activity-delays 2.3.0, hyperopt 0.3.0.
  Installazione con `uv pip`: 4 s.
- Serve **Java** (Split Miner e il layout del BPMN sono jar): OpenJDK 21.
- Macchina: 4 vCPU, 15 GB. I wall-clock di `diff` sono stati misurati con 3 discovery in
  parallelo; il tempo di SIMOD per fase (`simod_runtimes.json`) è quello da confrontare.

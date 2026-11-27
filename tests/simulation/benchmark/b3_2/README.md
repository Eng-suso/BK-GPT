# B3.2: discovery delle attese

Punto B3.2 di [`docs/vpt/PLAN.md`](../../../../docs/vpt/PLAN.md); schede, misure e decisioni nella voce
B3.2 di [`docs/vpt/LOG.md`](../../../../docs/vpt/LOG.md). Stato: **bloccato** (sintetici GO, reali NO-GO).

| Percorso | Cosa |
| --- | --- |
| `waiting.py` | attribuzione delle attese per causa dal solo log (libreria standard, pronta per il prodotto) |
| `attribution.py` | ritardi esterni per il simulatore (v1-v5), distribuzioni per Prosimos, timer nel BPMN |
| `attribution_eval.py` | scheda 2: cause giuste contro la verità dei sintetici, `attribution/<fase>_v1.json` |
| `run.py` | schede 1 e 3: driver sopra quello di G3b, configurazioni nuove soltanto |
| `report.py` | verdetti con le regole di G3b (risultati identici = pari), `results.md`, `verdicts.json` |
| `tools/simod_delays.py` | la sola fase dei ritardi di SIMOD 5.2.1 su uno scenario dato, con seed (venv di ricerca) |
| `tools/truth_logs.py` | i 20 modelli veri rigenerati con Prosimos, abilitazioni e timer nel log (venv di ricerca) |
| `results/<log>/<fase>/<config>.json` | un risultato per file, formato di G3b |

Comandi in [`docs/vpt/HANDOFF.md`](../../../../docs/vpt/HANDOFF.md), sezione `## B3.2`. La verità dei
sintetici (`/var/tmp/delir-b32/truth`) e la cache di SIMOD (`/var/tmp/delir-g3b/work`) non sono nel repo:
si rifanno (26 s la verità; la discovery di SIMOD non ha seed).

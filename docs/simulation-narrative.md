# SIM-24b · Testo per il cliente

La lettura calcolata di un'alternativa (SIM-24, `interpretation.ts`: dove si
sposta il vincolo, che scambio c'è fra tempo e costo) resta la fonte. Su
richiesta del consulente («Scrivi il testo per il cliente» nella lettura del
workspace) il modello la riscrive in due-quattro frasi da consegnare; il testo
entra anche nel decision record (SIM-27).

## Gate G4: nessun numero dal modello

| Passo | Dove |
|---|---|
| KPI della tabella del workspace, già formattati con segno e intervallo, con id `[K#]` e verdetto (`better`, `worse`, `unclear`, `same`) | `frontend/.../narrative.ts` |
| Lettura calcolata come contesto, **senza cifre** (tolte prima del prompt) | `backend/simulation/narrative.py` (`render`) |
| Il modello scrive il testo citando i numeri solo come `[K#]` | compito LLM `simulation_narrative` |
| Verifica: segnaposti esistenti, nessuna cifra fuori dai nomi del processo, al massimo 900 caratteri | `narrative.verify` |
| I segnaposti diventano i valori dei run | `narrative.verify` |

Un testo che non passa la verifica si rifiuta (502) e resta la lettura
calcolata, che il pannello mostra sempre. Una differenza «non certa» arriva al
modello come tale, e il prompt chiede di non presentarla come un guadagno.

## API

`POST /v1/workspace/bpmn-models/{id}/simulation-narrative` con
`{ language, as_is_name, scenario_name, kpis: [{label, value, verdict}], reading, names }`.

- `200`: `{ text, cited }`, con i valori al posto dei segnaposto.
- `503`: nessuna chiave del modello (o `DELIR_FAKE_LLM`).
- `502`: il modello non risponde, o il testo non è verificabile.

## Test

- `tests/simulation/test_simulation_narrative.py`: prompt senza numeri, verifica, rifiuti, route.
- `narrative.test.ts`, `ClientNarrative.ui.test.tsx`, `decisionRecord.test.ts`.
- `e2e/simulation-scenarios.spec.ts`: testo nella lettura e nel decision record, con axe.

## Eval

Golden set in `tests/golden/simulation/narrative.json` (6 confronti IT/EN, con KPI certi e incerti e nomi con cifre). In ogni CI il test L0 verifica che i casi siano coerenti; con il modello il run L1 (`test_simulation_llm_eval.py`, anche notturno) misura i testi verificati al primo colpo e la citazione dei KPI certi, in `tests/golden/reports/simulation_narrative.json`, e fallisce se un testo verificato contiene ancora una cifra non dei run. Che un KPI incerto non diventi un guadagno lo misurera' il giudice L2.

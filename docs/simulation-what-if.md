# SIM-23 · What-if in linguaggio naturale

Il consulente scrive una frase nel pannello scenario ("un approvatore in più e
Approva dura la metà"); DeliR la traduce in modifiche della bozza, le mostra
come anteprima e le applica solo su conferma. Nessun run parte dal what-if.

## Gate G4: dove serve l'LLM

Solo nella traduzione frase → modifiche tipizzate. Tutto il resto è codice:

| Passo | Dove | Chi decide |
|---|---|---|
| Frase + attività e ruoli della bozza, con id `[A#]` e `[R#]` | `backend/simulation/whatif.py` (`render`) | - |
| Traduzione in una delle cinque modifiche | compito `simulation_what_if` del gateway LLM | il modello |
| Id veri, limiti dei valori, una modifica per elemento | `whatif.parse` | codice: il resto si scarta e si conta (`rejected`) |
| Applicazione alla bozza | `frontend/.../whatIf.ts` (`applyWhatIf`) | codice, come gli esperimenti dell'advisor |
| Anteprima come patch dello scenario | `WhatIfComposer.tsx` (`diffScenario` + `useScenarioChanges`) | - |
| Applica, poi run | il consulente | il consulente |

## Le cinque modifiche

| `kind` | Effetto sulla bozza |
|---|---|
| `resource_units` | unità del ruolo (numero finale; un "+1" del modello diventa il numero finale nel backend); il ruolo va riconfermato |
| `activity_duration` | moltiplicatore, o nuova media in minuti: tutte le durate dell'attività (altri ruoli, categorie, soglie) scalano nella stessa proporzione |
| `skip_activity` | quota dei casi che salta l'attività, senza regola |
| `demand` | più o meno casi: il tempo fra due arrivi (e le fasce orarie) si divide per il fattore |
| `resource_cost` | costo orario del ruolo |

Ciò che il modello non sa tradurre torna in `not_understood` e il pannello lo
dice: si imposta a mano.

## API

`POST /v1/workspace/bpmn-models/{id}/simulation-what-if` con
`{ sentence, activities: [{id, name}], resources: [{id, name, units}] }`.

- `200`: `{ changes, not_understood, rejected }`.
- `503`: nessuna chiave del modello (o `DELIR_FAKE_LLM`): la funzione non parte.
- `502`: il modello non ha risposto o è uscito dallo schema.

## Test

- `tests/simulation/test_simulation_what_if.py`: parsing, limiti, operazione LLM, route (gateway finto).
- `whatIf.test.ts`, `WhatIfComposer.ui.test.tsx`: applicazione e componente.
- `e2e/simulation-what-if.spec.ts`: frase → anteprima → applica → run, con axe.

## Eval

Golden set in `tests/golden/simulation/what_if.json` (18 frasi IT/EN, ogni tipo di modifica, parti non traducibili). In ogni CI `tests/evals/l0_deterministic/test_simulation_llm_golden.py` verifica che ogni risposta attesa passi da `parse`. Con il modello: `DELIR_GOLDEN_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_simulation_llm_eval.py -s` (anche nel run notturno `golden-eval.yml`) scrive precision, recall e casi esatti in `tests/golden/reports/simulation_what_if.json`. Il set e' `draft_da_validare`: diventa un gate dopo la rilettura di un consulente e la prima baseline.

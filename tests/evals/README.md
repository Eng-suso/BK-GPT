# DeliR Eval System

`tests/<dominio>/` dice se il software funziona. `tests/evals/` dice se DeliR
e' intelligente quanto crediamo: una cartella per livello, dal piu' economico e
rigido al piu' vicino alla produzione.

Le categorie non sono alternative: un test L0 e' anche un test di regressione,
spesso di integrazione, a volte di sicurezza. La cartella dice **cosa protegge**
e **quando gira**, non l'unico nome che il test puo' avere.

| livello | cartella | cosa misura | quando gira | modello |
| --- | --- | --- | --- | --- |
| L0 | `l0_deterministic/` | invarianti: provenance, isolamento tenant, scope, scritture approvate, proiezioni stale, BPMN valido, compilatore sul golden set | ogni PR (CI/CD Pipeline) | no |
| L1 | `l1_golden/` | interviste → piano → BPMN contro la mappa di riferimento; loop di conformita' | notturno (`golden-eval.yml`) o a mano | si' |
| L1 | `l1_retrieval/` | da costruire: Recall@5, Precision@5, MRR, nDCG su query con evidence attese; memory recall | - | - |
| L2 | `l2_semantic/` | giudizio sulla mappatura: oggi la rubrica deterministica di `rubric.py`, poi JevEval per i giudizi bounded e G-Eval per quelli soggettivi | a mano | si' |
| L3 | `l3_trajectory/` | da costruire: tool giusto, ordine, chiamate inutili, stop prematuro, budget | - | - |
| L4 | `l4_production/` | da costruire: quality drift, costo e latenza per As-Is validato, correzioni umane | - | - |
| security | `security/promptfoo/` | da costruire: injection diretta e indiretta (PDF, Excel), jailbreak, tool malevoli, exfiltration, cross-tenant | - | - |

Una cartella nasce con il suo primo test, mai vuota.

Il piano completo (stack, metriche, fasi) e' nel doc "DeliR Evaluation System +
Jev — Piano".

## L0: le invarianti

Girano in CI con tutto il resto, senza modello e senza operazione EVAL aperta
(non c'e' spesa da attribuire). Se una di queste si rompe, DeliR non e' piu'
affidabile, qualunque cosa dica il resto della suite.

| test | invariante |
| --- | --- |
| `test_evidence_provenance.py` | ogni frase attribuita a una fonte ci sta davvero |
| `test_plan_provenance.py` | il piano si confronta con le fonti, non solo il disegno con il piano |
| `test_process_evidence_isolation.py` | la chat di un processo vede solo l'evidenza di quel processo |
| `test_evidence_scope.py` | l'evidenza resta dentro il proprio processo |
| `test_canonical_rls.py` | il tenant A non vede il tenant B (RLS sul Postgres canonical) |
| `test_scope_guard.py` | il `project_id` scelto dal modello non porta una scrittura fuori scope |
| `test_workspace_write_approval.py` | una scrittura sul workspace parte solo dopo il si' del consulente |
| `test_prompt_tool_contract.py` | un tool nominato in un prompt esiste nello scope che lo nomina |
| `test_kg_catalog.py` | il catalogo Postgres → Neo4j rispetta le sue invarianti |
| `test_kg_reproject.py` | Neo4j si ricostruisce da Postgres, e se e' indietro il retrieval lo dice |
| `test_evidence_survives_projection_outage.py` | con Neo4j e Mem0 giu' l'evidenza resta intera |
| `test_bpmn_soundness.py` | il BPMN e' sound: niente nodi irraggiungibili, vicoli ciechi o split impliciti |
| `test_golden_graph_metrics.py` | dal piano ideale il compilatore ridisegna la mappa di riferimento, a 1.0 |

## Eseguire

```
uv run pytest tests/evals/l0_deterministic -q                     # L0, gratis
DELIR_GOLDEN_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_golden_set.py -q -s
DELIR_AGENT_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_conformance_eval.py -q -s
DELIR_AGENT_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l2_semantic -q -s
```

I livelli col modello spendono davvero: senza le variabili si saltano, e ogni
eval gira dentro la sua operazione EVAL (`conftest.py`), cosi' la spesa nel
registro non si confonde con quella del prodotto. I casi del golden set e il
loro formato sono in `tests/golden/README.md`.

# Test del backend

`tests/<dominio>/` dice se il software funziona; `tests/evals/` dice se DeliR e'
intelligente quanto crediamo (vedi `tests/evals/README.md`).

| cartella | cosa contiene |
| --- | --- |
| `agents/` | graph, routing, budget, progresso, handoff process -> canvas |
| `bpmn/` | serializer, eventi, gateway, layout, review, piano di modellazione |
| `chat/` | allegati, modalita', contratto del turno, postura, trascrizione |
| `conformance/` | il revisore di conformita' |
| `evidence/` | fonti, parser, Evidence Bucket, pipeline evidenza -> piano |
| `knowledge_graph/` | proiezione su Neo4j, ingestione, retrieval, entity resolution |
| `memory/` | Mem0, memoria del consulente, semantica, episodica, procedurale |
| `llm/` | gateway, registro dei consumi, timeout, tracer, modello dei test |
| `plan/` | estrazione e consolidamento del piano |
| `server/` | avvio, contratto API, capacita', code |
| `simulation/` | simulazione e replay |
| `workspace/` | workspace, progetti, notifiche, ricerca |
| `evals/` | il DeliR Eval System, un livello per cartella |
| `fixtures/`, `golden/` | dati: interviste, BPMN, casi del golden set |

## Marker

| marker | quando gira |
| --- | --- |
| `smoke` | controlli rapidi dopo ogni deploy: l'app parte, risponde, si difende, il contratto col frontend regge. Circa 20 secondi |
| `live_llm` | solo con `DELIR_LIVE_LLM=1`, sul modello dei test (`tests/live_llm.py`), mai su OpenAI per default |
| `agent_eval` | solo con `DELIR_AGENT_EVAL=1`: eval dell'agente col modello |

## Eseguire

```
uv run pytest tests -q            # tutta la suite, senza modello
uv run pytest -m smoke -q         # smoke, dopo un deploy
uv run pytest tests/evals -q      # l'Eval System, senza modello
```

Lo stack dati di test vive in `ops/docker-compose.test.yml` (tmpfs, porte
55301/7688); il conftest lo migra a ogni sessione. Per uno stack separato -
per esempio quando un altro branch ha migrato quello condiviso piu' avanti del
tuo - `DELIR_TEST_PG_PORT` e `DELIR_TEST_NEO4J_PORT` puntano il conftest altrove.

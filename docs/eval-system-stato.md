# DeliR Evaluation System: dove siamo e come riprendere

Stato al 6 ottobre 2026. Serve a chi riprende il lavoro da un'altra sessione
(cloud, da telefono): cosa c'e' gia', cosa manca, cosa e' bloccato e da chi.

## Dove seguire il lavoro

| cosa | dove |
| --- | --- |
| Il piano, con le fasi e le spunte | [DeliR Evaluation System + Jev - Piano](https://claude.ai/code/artifact/89acee8e-8c94-44dc-9b05-b877b7e57689) |
| La revisione per il consulente (95 righe da approvare) | [Revisione golden set e calibrazione](https://claude.ai/code/artifact/f5da8937-a65f-4689-983f-5a7f2eb25586) |
| La mappa degli eval nel repo | `tests/evals/README.md` |
| La mappa dei test nel repo | `tests/README.md` |

Il piano su claude.ai e' la fonte di verita' sullo stato delle fasi: ogni blocco
finito si spunta li', con il numero della PR.

## Cosa c'e' (tutto su main)

| PR | fase | cosa |
| --- | --- | --- |
| #39 | 0 | test divisi per dominio (`tests/<dominio>/`), eval per livello (`tests/evals/l0_deterministic`, `l1_golden`, `l2_semantic`) |
| #41 | 2 | golden set sul contratto v2: evidenze legate alle fonti, claim, conflitti, percorsi di eccezione; ogni citazione verificata alla lettera da un test L0 |
| #43 | 3 | benchmark del retrieval (`l1_retrieval`): 16 domande, baseline lessicale recall@5 0.906, MRR 0.813 |
| #45 | - | i test col modello girano sul **modello dei test** (Gemini o Ollama, `DELIR_TEST_LLM_*`), mai su OpenAI per default; golden notturno riparato |
| #48 | 4 | il giudice L2 (`tests/evals/judge.py`, compito `eval_judge`) e il set di calibrazione (18 domande) |
| #49 | 6 | metriche di traiettoria e 3 traiettorie attese (`l3_trajectory`), ognuna fondata su una regola del prodotto citata alla lettera |
| #51 | 9 | suite smoke (`uv run pytest -m smoke`, 18 test, circa 20 s) |

## Cosa manca, in ordine

| # | lavoro | stato | sblocca chi |
| --- | --- | --- | --- |
| 1 | Chiave del modello dei test su GitHub e nel `.env` | **bloccato** | Sohayb: secret `DELIR_TEST_LLM_API_KEY`, variabili `DELIR_TEST_LLM_BASE_URL` e `DELIR_TEST_LLM_MODEL` |
| 2 | Primo run del golden notturno sul modello dei test, e verifica che l'estrattore regga l'output strutturato su Gemini | dopo 1 | `gh workflow run golden-eval.yml` |
| 3 | Firma delle etichette (golden set + calibrazione) | **bloccato** | un consulente, o Sohayb, sul doc di revisione |
| 4 | Dopo la firma: `status` a `validated` nei tre file, baseline da `tests/golden/reports/`, il giudice diventa gate (kappa >= 0.6) | dopo 2 e 3 | - |
| 5 | Runner L3: far girare l'agente di processo sulle 3 traiettorie col modello dei test | dopo 1 | - |
| 6 | Retrieval: ramo vettoriale (opt-in) e metriche di memoria (recall, stale, wrong-scope) | dopo 1 | - |
| 7 | Load test (Locust consigliato, con `DELIR_FAKE_LLM=1`), poi stress e scalability | **da decidere** | Sohayb: strumento e ambiente |
| 8 | POC Jev su routing, evidence support, entity resolution | **bloccato** | Sohayb: accesso early access TypeSafe e quali dati possono uscire |
| 9 | Security L3: Promptfoo red team | libero | - |

Il primo lavoro libero, senza chiavi ne' decisioni, e' il 9.

## Regole di lavoro

- Un branch per blocco, tanti commit piccoli, PR, CI verde, merge su main, e
  subito un branch nuovo per il blocco dopo.
- Commit a nome Sohayb Raqaq, **senza** trailer `Co-Authored-By`.
- Titolo della PR in Conventional Commits, `type(scope): sommario` (max 72):
  CodeRabbit lo blocca altrimenti. CodeRabbit non parte da solo: commento
  `@coderabbitai review` sulla PR, e di nuovo dopo ogni push.
- Dopo ogni commit `git status --short` vuoto; prima del push, se si toccano
  migrazioni, `alembic heads` con una testa sola su entrambe le catene.
- I test non toccano mai il database di sviluppo: niente `.env` copiato nei
  worktree, niente `--noconftest`; il conftest sposta i DSN sullo stack di test,
  e `DELIR_TEST_PG_PORT` / `DELIR_TEST_NEO4J_PORT` scelgono uno stack separato.
- I test col modello usano il modello dei test; OpenAI resta per la produzione e
  per le prove a mano.
- Altre sessioni lavorano in parallelo e mergiano su main: prima di mergiare
  `gh pr view N --json state`, prima di pushare `git fetch` e merge di main.

## In una sessione cloud

Nel cloud di solito non ci sono Postgres e Neo4j: i test che li usano si
saltano o falliscono in locale, e il giudice e' la CI della PR. Girano senza
database i test L0 puri, per esempio:

```
uv run pytest tests/evals/l0_deterministic/test_golden_contract.py tests/evals/l0_deterministic/test_retrieval_metrics.py tests/evals/l0_deterministic/test_trajectory_metrics.py tests/evals/l0_deterministic/test_judge.py -q
```

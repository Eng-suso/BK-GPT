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
| L1 | `l1_golden/` | interviste → piano → BPMN contro la mappa di riferimento (disegno, handoff, eccezioni) e cio' che il piano sa (evidenze, claim, conflitti); loop di conformita' | notturno (`golden-eval.yml`) o a mano | si' |
| L1 | `l1_retrieval/` | 16 domande da consulente sulle interviste del golden set: recall@5, precision@5, MRR, nDCG@5 del ramo lessicale di `graph_retrieve`, piu' nessun chunk fuori scope. Da costruire: ramo vettoriale e memoria (recall, stale, wrong-scope) | ogni PR (deterministico) | no |
| L2 | `l2_semantic/` | giudizio dove una regola non basta. Il giudice (`judge.py`, compito `eval_judge` sul modello dei test) risponde a domande chiuse si'/no con confidenza, o da' un voto 1-5 seguendo i passi scritti di un criterio. Prima di giudicare l'agente si calibra contro un umano (`calibration_discovery.json`: 18 domande di discovery "necessarie?", accuracy e kappa). La rubrica deterministica di `rubric.py` resta per la mappatura | a mano | si' |
| L3 | `l3_trajectory/` | il percorso dell'agente, non la risposta: tool che deve chiamare (anche con l'operazione giusta), tool vietati, chiamate ripetute, budget (`trajectory_metrics.py`). Tre traiettorie attese dell'agente di processo, ognuna con la regola del prodotto che la impone citata alla lettera. Da costruire: il runner che fa girare l'agente sul modello dei test e le misura | - | - |
| L4 | `l4_production/` | da costruire: quality drift, costo e latenza per As-Is validato, correzioni umane | - | - |
| security | `security/promptfoo/` | da costruire: injection diretta e indiretta (PDF, Excel), jailbreak, tool malevoli, exfiltration, cross-tenant | - | - |

Una cartella nasce con il suo primo test, mai vuota.

Il piano completo (stack, metriche, fasi) e' nel doc "DeliR Evaluation System +
Jev — Piano". Dove siamo arrivati, cosa manca e chi lo sblocca:
`docs/eval-system-stato.md`.

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
| `test_golden_contract.py` | il golden set cita le sue fonti alla lettera, e ogni elemento obbligatorio ha un passo che lo dice |
| `test_retrieval_metrics.py`, `test_retrieval_dataset.py` | le metriche di retrieval dicono il vero, e i passi attesi stanno nelle interviste alla lettera |
| `test_trajectory_metrics.py`, `test_trajectory_specs.py` | le metriche di traiettoria dicono il vero, e ogni traiettoria attesa si regge su una regola ancora scritta nel prodotto, con tool e argomenti che esistono |
| `test_judge.py`, `test_judge_calibration_set.py` | il giudice L2 passa dal gateway col suo compito, l'accordo con un umano si calcola giusto, il set di calibrazione e' utilizzabile |
| `test_golden_graph_metrics.py` | dal piano ideale il compilatore ridisegna la mappa di riferimento, a 1.0 |
| `test_agent_outcomes.py` | un turno vero dell'agente (`outcome_harness.py`) con un modello che sbaglia: injection, progetto fuori scope, disegno cambiato da un collega, database giu'. Lo stato cambia solo quando deve, e nessun esito finto arriva al modello |
| `test_bef4llm.py` | le metriche BEF4LLM dicono il vero su modelli scritti a mano, e ogni BPMN che il compilatore produce dal golden set passa lo schema XSD di BPMN 2.0 |

## BEF4LLM: DeliR sulla scala di un benchmark pubblicato

`bef4llm.py` implementa il framework di Lauer et al., *Assessing the business
process modeling competences of large language models* (Information Systems
142, 2026): 39 metriche su quattro dimensioni, ognuna in [0, 1].

| punteggio | metriche | cosa dice |
| --- | --- | --- |
| `Q_val` | 1 | l'XML passa lo schema XSD di BPMN 2.0 (`bef4llm_xsd/`). Se no, il resto non si calcola |
| `Q_syn` | 16 | regole di BPMN: start/end, archi ammessi, gradi dei nodi, split richiusi da un join |
| `Q_prag` | 15 | leggibilita': dimensione, densita', gateway, partizionabilita', concorrenza, con le soglie del paper |
| `Q_sem` | 7 | somiglianza con un BPMN di riferimento: etichette, struttura, comportamento |
| `Q_qual` / `Q_total` | - | media delle tre qualita' / piu' la validita' |

```
uv run python -m tests.evals.bef4llm candidato.bpmn                      # Q_val, Q_syn, Q_prag
uv run python -m tests.evals.bef4llm candidato.bpmn --reference rif.bpmn # anche Q_sem
uv run python -m tests.evals.bef4llm candidato.bpmn --json               # ogni metrica
```

Nel golden notturno (`l1_golden/test_golden_set.py`) il disegno dell'LLM e'
confrontato col BPMN del piano ideale e il punteggio finisce nel rapporto,
chiave `bef4llm`. E' una lettura, non un gate.

Il compilatore sul piano ideale, oggi (riferimento per i run futuri):

| caso | Q_val | Q_syn | Q_prag | regole che cadono |
| --- | --- | --- | --- | --- |
| `esaote_ciclo_passivo` | 1.00 | 0.87 | 0.82 | fine con piu' entrate, split XOR senza join, task con piu' entrate |
| `facility_segnalazioni_guasti` | 1.00 | 0.84 | 0.83 | le stesse, piu' il pool esterno senza processo (black box) |

Nel paper i migliori modelli open-source stanno intorno a 0.86-0.90 di
`Q_syn`, 0.85-0.90 di `Q_prag`, 0.53-0.58 di `Q_sem`.

Non e' una copia bit a bit: il codice degli autori non e' raggiungibile da qui
e alcune formule del PDF hanno esponenti e pedici persi. Dove la formula e'
illeggibile vale la fonte che il paper cita (Mendling, Cardoso, Vanderfeesten,
Dijkman), scritto accanto a ogni metrica in `bef4llm.py`. Confrontare con le
tabelle del paper come ordine di grandezza, non alla terza cifra.

## Eseguire

```
uv run pytest tests/evals/l0_deterministic -q                     # L0, gratis
uv run pytest tests/evals/l1_retrieval -q -s                       # retrieval lessicale, gratis
DELIR_GOLDEN_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_golden_set.py -q -s
DELIR_AGENT_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_conformance_eval.py -q -s
DELIR_AGENT_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l2_semantic -q -s
```

I livelli col modello non usano OpenAI: girano sul **modello dei test**, un
endpoint compatibile OpenAI gratuito o economico (`tests/live_llm.py`). OpenAI
resta il modello della produzione e delle prove a mano.

```
# Gemini (gratuito; le fonti del golden set sono anonimizzate, mai dati clienti)
DELIR_TEST_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
DELIR_TEST_LLM_API_KEY=<chiave di Google AI Studio>
DELIR_TEST_LLM_MODEL=<un modello Gemini Flash>

# Ollama in locale (gratuito, i dati non escono dal PC; senza GPU e' lento)
DELIR_TEST_LLM_BASE_URL=http://localhost:11434/v1
DELIR_TEST_LLM_API_KEY=ollama
DELIR_TEST_LLM_MODEL=<un modello scaricato con ollama pull>
```

Senza modello dei test un eval col modello si salta, invece di ripiegare su
OpenAI; pagarlo resta una scelta dichiarata (`DELIR_TEST_LLM_ALLOW_OPENAI=1`).
Sul modello dei test gli embedding sono spenti: lo schema vuole i vettori a
1536 dimensioni di OpenAI, e il retrieval usa il solo ramo lessicale. Il job
notturno legge le stesse variabili dalle variabili e dai secret del repository.

Ogni eval gira dentro la sua operazione EVAL (`conftest.py`), cosi' i consumi
nel registro non si confondono con quelli del prodotto. I casi del golden set e il
loro formato sono in `tests/golden/README.md`.

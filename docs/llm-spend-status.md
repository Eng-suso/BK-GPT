# Spesa LLM — stato dei lavori

Documento vivo. Il piano sta in [`llm-gateway-plan.md`](llm-gateway-plan.md) e
non si tocca: e' la direzione. Qui c'e' cosa e' stato fatto, cosa manca, e
qual e' il prossimo passo.

**A chi serve:** a piu' sessioni agente in parallelo, e a Sohayb per sapere dove
siamo senza rileggere i diff.

**Se stai aprendo una sessione nuova, leggi prima §⑤:** senza un database
tuo, i test di questo repo si rompono in modo che sembra un bug del codice e non
lo e'.

**Come si usa.** Chi prende in mano il lavoro legge §② e fa quello. Chi lo posa
aggiorna §① (cosa ha chiuso), §② (il prossimo passo, uno solo) e §⑥ (la riga di
log). Un passo non si dichiara fatto se i suoi test non sono verdi: §① distingue
*scritto* da *verificato*, ed e' la distinzione che vale.

Ultimo aggiornamento: 2026-09-24.
Branch di lavoro: `chore/llm-t5` (worktree `.claude/worktrees/llm-t5`).

---

## ① Stato

### P0 — Fermare gli sprechi

| # | Cosa | Stato |
| --- | --- | --- |
| P0.1 | Test senza chiave del provider (invariante L6) | **fatto, verificato** |
| P0.2 | Un solo livello di retry invisibile: SDK a 0 | **fatto, verificato** |
| P0.3 | Timeout proporzionato alla lunghezza dell'input | **fatto, verificato** |
| P0.4 | Progetti e chiavi separati dev / eval / prod, con tetto | **non iniziato** — serve Sohayb (§④) |
| P0.5 | Tracing LangSmith spento | **non fatto** — una riga in `.env`, §④ |
| P0.6 | Riferimenti rotti nel piano parziale intercettati prima del merge | **rinviato a P2** (§④) |

**Suite verde a P0 chiuso: 1256 passed, 14 skipped, 1 xfailed, 0 failed**
(23 min 28, su database isolato). I conti tornano rispetto alla passata di
partenza (1240 passed, 9 failed, 2 h 24 sotto contention): +16 test nuovi
(1240 + 16 = 1256), e gli skip da 11 a 14 sono esattamente i tre casi live
appena dichiarati.

Dei 9 fallimenti di partenza: 1 era la migrazione di un'altra sessione sul
database condiviso (§⑤), 1 era contention fra suite — poi verde da solo — e 7
erano veri.

**P0.1 — i test non pagano piu' (L6).** Era il buco piu' grosso e il piu'
economico da chiudere. I test live erano gated sulla *presenza* della chiave
(`skipif(not settings.openai_api_key)`): con un `.env` popolato — cioe' sempre,
in sviluppo — non si skippavano, giravano e pagavano.

Il default e' invertito. Ora:

- `tests/live_llm.py` — l'opt-in: `DELIR_LIVE_LLM=1`. La chiave e' un
  requisito, non un permesso.
- `tests/conftest.py::_provider_calls_are_opt_in` — autouse: azzera
  `openai_api_key` e `tavily_api_key` nei settings **e** cancella le env var
  omonime, perche' `langchain_openai` con `api_key=None` ricade sull'ambiente.
- Svuota anche le cache dei client (7 builder `lru_cache` + il singleton di
  `entity_resolution`): un test live che gira per primo lasciava in cache un
  client vero, e i successivi chiamavano il provider malgrado i settings.
- `backend/llm_config.py::MissingProviderKey` — costruire un client senza chiave
  e' un errore di configurazione dichiarato, non una chiamata che parte.
- `tests/test_no_live_llm_by_default.py` — 5 test che verificano il meccanismo.
  **4 passed, 1 skipped** (lo skip e' corretto: e' il test `live_llm`).
- La vecchia fixture `mock_env` e' stata rimossa: nessuno la usava, e non
  funzionava comunque (`settings` e' costruito all'import, cambiare le env var
  dopo non lo tocca).

Convertiti a opt-in gli 11 moduli che pagavano: `test_gateway_memory`,
`test_client_scoped_recall`, `test_kg_vector_retrieval`, `test_entity_resolution`
(`TestVectorPath` + il test worker/Neo4j), `test_kg_ingest_queue` (E2E dal tool),
`evals/test_golden_set`, `evals/test_canvas_modeling_eval`,
`evals/test_conformance_eval`, `test_product_language`, `test_mem0_projection`,
`test_semantic_episodic_mirror`.

**Gli ultimi tre non nominavano la chiave, e sono i piu' istruttivi.** Cercare
`skipif(not settings.openai_api_key)` trova solo i test che sapevano di pagare.
`test_mem0_projection` e `test_semantic_episodic_mirror` gateavano sulle sole
DSN, ma lo specchio passa da Mem0, che estrae i fatti con un LLM e li indicizza
con un embedder: passavano solo perche' la chiave c'era. La spesa implicita non
si trova con una grep: si trova azzerando la chiave e guardando cosa si rompe.
Per il prossimo giro: **un test che si rompe quando togli la chiave era un test
che pagava.**

**P0.2 — retry.** `model_max_retries` da 1 a **0**. I retry dell'SDK erano il
peggior tipo di spesa: invisibili (non lasciano traccia, non si contano),
indiscriminati (ritentano anche un timeout di un compito lungo) e moltiplicativi
sopra a quelli applicativi. Il caso peggiore per fonte passa da **20 tentativi a
10** (era 2 SDK x 2 per fonte x 5 di coda).

Non e' un taglio uniforme, e la regola che lo governa e' una sola: **il retry
dell'SDK si toglie dove esiste gia' qualcosa che ritenta, e si tiene dove il
guasto arriva a una persona che aspetta.** Quindi tre valori invece di uno:

| Setting | Valore | Perche' |
| --- | --- | --- |
| `model_max_retries` | **0** | compiti task-scoped: dietro c'e' la coda, con backoff, e il guasto e' classificato |
| `agent_max_retries` | 1 | il turno di chat non ha una coda dietro: un 429 transitorio diventerebbe un errore in faccia al consulente |
| `transcription_max_retries` | 1 | chiamata singola su un upload in corso; rifare l'upload costa piu' che ritentare |

Gli ultimi due sono nuovi solo come nome: il comportamento di chat e
trascrizione non cambia rispetto a prima.

**I numeri veri erano peggiori di quelli del piano, e la ragione va ricordata.**
`.env` conteneva `MODEL_MAX_RETRIES=2` e `MODEL_TIMEOUT_SECONDS=60`, cioe' il
doppio dei retry e un timeout diverso rispetto ai default del codice (1 e 45 s).
Il caso peggiore per fonte non era 20 tentativi ma **30** (3 SDK x 2 per fonte x
5 di coda), e su cinque interviste 150. Il piano descriveva la configurazione
*deployata*; chi legge solo i default del codice misura un sistema che non esiste.
`MODEL_MAX_RETRIES` e' stato portato a 0 in `.env` (backup `.env.bak-p0`), e
`MODEL_TIMEOUT_SECONDS=60` ora e' solo il pavimento, quindi va bene com'e'.

Per questo il test sui retry non asserisce il valore effettivo ma **il default
dichiarato piu' l'ordinamento** fra i tre livelli: il valore effettivo lo decide
`.env`, ed e' esattamente da li' che lo spreco arrivava senza che nessuno lo
vedesse.

**P0.3 — timeout proporzionato.** `llm_config.timeout_for_input(characters)`:
pavimento `model_timeout_seconds` (45 s) + 15 s per 1.000 caratteri, tetto 300 s.
Un'intervista da 4.000 caratteri passa da 45 s a 105 s. All'epoca la cache
dell'estrattore era chiavata su scaglioni di 2.000 caratteri
(`process_understanding._timeout_bucket`), altrimenti la prima nota corta
avrebbe fissato il timeout del caso breve per ogni intervista successiva; con
t.5 quella cache non esiste piu' e la lunghezza arriva al gateway esatta.

### P1 — Misurare tutto

| # | Cosa | Stato |
| --- | --- | --- |
| P1.1 | Operazione corrente (`contextvar`), con eredita' nei thread | **fatto, verificato** |
| P1.2 | Registro dei compiti (`TaskProfile`), 12 compiti | **fatto, verificato** |
| P1.3 | Registro dei consumi su Postgres + costo stimato | **fatto, verificato** |
| P1.4 | `llm.run` che rifiuta una chiamata senza operazione (L2) e registra sempre (L4) | **fatto, verificato** |
| P1.5 t.1 | I punti d'ingresso aprono l'operazione | **fatto** (chat turn da verificare, sotto) |
| P1.5 t.2 | Il pool di estrazione la eredita nei thread | **fatto, verificato** |
| P1.5 t.3 | reranker + entity resolution sul gateway | **fatto, verificato** |
| P1.5 t.4 | embedding sul gateway | **fatto, verificato** |
| P1.5 t.5 | percorso caldo (`process_understanding`, audit, consolidamento) | **fatto, verificato** |
| P1.5 t.6 | `agent.py` (streaming) | **non iniziato** ← §② |
| P1.6 | L1 in CI: `ChatOpenAI` / `openai` vietati fuori da `backend/llm/` | **non iniziato** |

**t.1 — aprono l'operazione:** `plan_worker` (PLAN_SYNTHESIS), `conformance_worker`
(CONFORMANCE_AUDIT), `ingest_worker` (KG_INGESTION) e il turno di chat
(CHAT_TURN, in `agent_runtime.stream_agent_events`).

Il turno di chat usa `new_operation` + `adopt` invece di `with operation(...)`, e
la ragione va ricordata: `stream_agent_events` e' un **generatore**, e un
`ContextVar` legato dentro il corpo di un generatore resta visibile al chiamante
fra un `next()` e l'altro, rilasciandosi solo quando il generatore si chiude. Se
nessuno lo chiude, resta legato. L'operazione si costruisce nella richiesta - dove
tenant e scope ci sono - e si adotta nel thread dell'agente, che e' dove il lavoro
succede.

~~**Buco dichiarato:** il turno di chat non ha un test di integrazione.~~ Chiuso
con `tests/test_llm_spend_e2e.py`: si chiama `stream_agent_events` vera, con
l'agente sostituito da un doppio che chiede un compito al gateway, e si guarda
se la riga compare nel registro con `operation_kind = chat_turn`. Se l'aggancio
fra la richiesta e il thread si rompe, quel test diventa rosso.

**t.3 — quello che e' *sparito* e' il risultato migliore.** Reranker ed entity
resolution avevano ognuno un client costruito in casa, una cache globale e un
percorso d'errore per l'init fallito. Ora chiedono al gateway e nel modulo resta
la sola domanda che il chiamante deve poter fare: «e' possibile, adesso,
riordinare / dare un giudizio?». Il singleton `_llm_singleton` non c'e' piu', e
con lui una fonte di stato condiviso fra test.

In entrambi resta il **seam dell'iniezione**: un modello passato a mano bypassa il
gateway, ed e' quello che usano i test.

**t.4 — l'embedding ha un ingresso suo, e non poteva non averlo.** I token di una
risposta di embedding stanno in `response.usage.prompt_tokens`, non in
`usage_metadata`: leggerli col lettore della chat avrebbe dato **zero token su
tutto il volume dell'ingestione**, cioe' esattamente dove il volume sta. Quindi
`llm.embed()` e `usage.extract_embedding_tokens()` separati da `run()`.

Due cose che il piano non diceva e che qui sono state decise:

- **il modello dell'embedding non e' una scelta, e' un contratto.**
  `TaskProfile` ha ora `model_name`: per la chat resta `settings.openai_model`,
  per l'embedding e' `text-embedding-3-small`, perche' quel nome decide la
  dimensione dei vettori gia' scritti (INV-4). Il valore sta in due posti —
  `tasks.py` e `memory/embeddings.py` — di proposito, per non far dipendere il
  registro dei compiti dalla memoria, e un test tiene i due allineati;
- **`embed_texts` non degrada piu' su tutto.** Il contratto «mai solleva, torna
  `None`» resta per i guasti del fornitore, ma `OperationNotOpen` risale. E' lo
  stesso ragionamento di t.3: un punto d'ingresso dimenticato spegnerebbe il
  retrieval vettoriale in silenzio, e il sintomo arriverebbe al consulente come
  «le risposte sono peggiorate», senza niente da guardare.

Censiti tutti i percorsi che embeddano, perche' da adesso uno scoperto e' un
errore invece di una degradazione muta: `ingest_worker` e i tool della chat
erano gia' coperti da t.1; `scripts/kg_resolve_entities.py` no, e ora apre
un'operazione per cliente. `mirror.mirror_evidence` arriva sempre da un tool
dell'agente, quindi eredita il turno.

**t.3bis — i playbook, la coda di t.3.** `memory/procedural/extraction.py` era
nell'elenco della tappa e non era stato migrato: costruiva ancora due
`ChatOpenAI` suoi, quindi l'apprendimento del prodotto era spesa senza nome.
Ora chiede al gateway con `PLAYBOOK_EXTRACTION` e `PLAYBOOK_GENERALIZATION`.

**t.5 — il percorso caldo, e una cache che non serviva piu' a nessuno.**
`process_understanding` (estrazione + giudizio di qualita'),
`agents/conformance_audit` e `agents/plan_consolidation` chiedono il compito al
gateway. Con loro finisce la migrazione dei compiti del prodotto: fuori restano
solo `agent.py` (t.6) e la trascrizione.

Il pezzo di pulizia piu' utile e' quello **tolto**. L'estrattore aveva
`_understanding_llm` con `lru_cache(maxsize=8)` chiavata su `_timeout_bucket`,
cioe' su scaglioni di 2.000 caratteri: serviva perche' il timeout dipende dalla
lunghezza dell'input e una cache a chiave singola avrebbe fissato il timeout del
caso breve per tutte le interviste. Col gateway il client lo costruisce chi sa
gia' il timeout, quindi la fascia, la cache e il loro test sono spariti, e
l'estrazione passa la **lunghezza vera** dell'intervista invece di
un'approssimazione per eccesso.

Il seam dei test cambia di conseguenza, ed e' il punto su cui il doc avvisava:
chi sostituiva `_understanding_llm` ora sostituisce `llm_run`. Sono due test,
`test_bpmn_semantic` e `test_no_live_llm_by_default`.

Anche il giudizio di qualita' aveva un `except Exception` che degradava a
"fallback conservativo": adesso `OperationNotOpen` risale. Degradarla avrebbe
dato un giudizio prudente **sempre**, e un piano non valutato si sarebbe letto
come un piano mediocre — un guasto travestito da opinione.

**Pulizia:** il segnaposto `GATEWAY` era copiato in due moduli (entity
resolution e playbook). Ora e' uno solo, in `backend/llm`, e un test verifica
che i due nomi puntino allo stesso oggetto: due segnaposti che devono
comportarsi uguale sono due cose che possono divergere.

**La regola L2 vale adesso in tutti e quattro i moduli best-effort.** t.3 aveva
risolto il problema cablando gli ingressi; restava che l'`except` largo, se un
ingresso nuovo si dimenticava, avrebbe comunque inghiottito il rifiuto. Adesso
`OperationNotOpen` risale in `reranker`, `entity_resolution` (in **due** punti:
`adjudicate` e il wrapper piu' largo che lo chiama), `memory/embeddings` e
`procedural/extraction`. Un guasto del fornitore degrada come prima; un punto
d'ingresso dimenticato no, perche' non e' un guasto: e' un bug.

### Quello che l'e2e ha trovato, e che nessun test unitario poteva trovare

`tests/test_llm_spend_e2e.py` fa il percorso vero - coda, worker, embedding,
registro su Postgres - e finge **solo il confine di rete**. Ha trovato subito un
difetto che tutti i doppi nascondevano: **il registro aveva due spazi di id
nella stessa colonna.** La chat e la sintesi del piano scrivono `project_id`
con l'id *workspace*; l'ingestione lavora con l'id *canonical*, che e' un id
diverso dello stesso progetto (`memory/scope.resolve` mappa l'uno sull'altro).
Sommare la spesa per progetto avrebbe diviso in due ogni progetto, e il totale
sarebbe rimasto giusto: il difetto peggiore, perche' nessun numero sembra
sbagliato.

Il pacchetto di evidenza ora viaggia con gli id workspace accanto a quelli
canonical (`workspace_project_id` / `workspace_process_id` nel payload della
coda, **fuori** da `EVIDENCE_KEYS` perche' alla scrittura non servono), e
l'operazione dell'ingestione usa quelli. I job accodati prima ricadono sugli id
canonical: meglio una riga riconoscibile che una senza progetto. Il gateway e' il percorso normale, non
l'unico.

Una cosa a cui stare attenti su questi due: sono `best-effort` con un `except`
largo. Se l'operazione non fosse aperta, il gateway solleverebbe, l'`except` lo
inghiottirebbe, e si perderebbe rerank ed entity resolution **in silenzio** — il
grafo accumulerebbe duplicati senza dirlo. E' la ragione per cui t.1 doveva
chiudersi prima di t.3, e non era ovvio nell'ordine scritto ieri.

Il pacchetto e' `backend/llm/`: `operation.py`, `tasks.py`, `prices.py`,
`usage.py`, `gateway.py`. `backend/llm_config.py` resta il posto della policy sui
parametri del client e il gateway lo usa — non l'ha sostituito. 36 test in
`tests/test_llm_gateway.py`, ruff e mypy verdi (`backend/llm` e' entrato sotto
mypy).

**Finche' P1.5 non e' fatto, il gateway non misura niente in produzione**: i punti
di chiamata costruiscono ancora il loro client. La fondazione c'e' ed e'
verificata; il valore arriva con la migrazione.

Tre cose apprese scrivendolo, che valgono piu' del codice:

1. **`with_structured_output()` perde `usage_metadata`.** Il parsato e' un oggetto
   pydantic; i token vivono sull'`AIMessage` grezzo. Quasi tutte le nostre
   chiamate sono strutturate: misurandole nel modo ovvio avremmo letto **zero
   token su tutto**, e creduto di misurare. Il gateway usa `include_raw=True` e
   tiene entrambi. Chi tocchera' quel punto: non togliere `include_raw`.
2. **`max_retries` va al costruttore, non a `bind`.** `bind` aggiunge kwargs alla
   chiamata API, e il fornitore rifiuta un parametro che non conosce. Il primo
   test non lo vedeva perche' il doppio ignorava `bind`: ora c'e' un test contro
   il costruttore vero. Un doppio piu' permissivo del vero nasconde esattamente
   i bug che stai cercando.
3. **`reasoning_effort="medium"` era un default, non una scelta**, applicato a
   sette compiti diversi. Nel registro dei compiti i due che rispondono dentro
   uno schema strict (entity resolution, rerank) sono a `none`: lo schema fa il
   lavoro. Quanto valga si vedra' col registro, ed e' il primo esperimento da
   fare appena P1.5 e' in piedi.

### P2–P5

Non iniziati. Vedi il piano.

---

## ② PROSSIMO STEP

**t.6 — `agent.py`**, l'ultimo punto di chiamata del prodotto: e' l'unico che fa
streaming verso il frontend, e il gateway oggi non strema. Serve un ingresso che
ritorni l'iteratore e registri alla fine (`stream_usage=True` c'e' gia'). E'
anche l'unico file rimasto che tocca `llm/gateway.py`, quindi chi lo prende ci
lavora da solo.

Con t.6 viene dietro anche `graphs/routing_contracts.py`, che non costruisce
nessun client ma riceve `context_router_llm` da `agent.py`: il compito
`CONTEXT_ROUTING` esiste gia' nel registro e oggi non lo usa nessuno. Chi fa
t.6 deve aprire **due** ingressi, non uno, o l'instradamento resta spesa
attribuita al modello di chat.

Poi, in ordine:

**Le due code**, piccole e parallele: l'operazione `EVAL` attorno a
`tests/evals/`, che girano col modello vero, e la trascrizione in
`api/routes/audio.py` (§③.5), che e' l'unico punto di chiamata `async`.

Poi **P1.6**, la regola L1 in CI: una regola ast-grep che vieta `ChatOpenAI`,
`openai`, `OpenAIEmbeddings` fuori da `backend/llm/`. Va messa **dopo** la
migrazione — e "dopo" vuol dire dopo le code qui sopra, non solo dopo t.6:
finche' resta un modulo che costruisce il suo client la regola nasce rossa, e
una regola rossa si impara a ignorare. Le regole stanno in
`.coderabbit/ast-grep-rules/`, una per file.

Prima di P3 (budget con prenotazione e saldo) servono due settimane di numeri
veri. Non e' solo la soglia a dipendere dai dati: la *forma* del meccanismo lo e'.

---

## ③ Cosa manca, in ordine di valore

1. **Registro dei consumi** (P1). Senza, ogni scelta successiva e' a occhio.
2. **Artefatti con dipendenze** (P2, §4.2 del piano). E' l'unica leva che cambia
   l'ordine di grandezza invece di una percentuale. Il lavoro concreto:
   `evidence_source_set_id` portato al livello della singola fonte.
3. **`reasoning_effort` per compito.** Il default di
   [`chat_openai_kwargs`](../backend/llm_config.py) e' `medium`, e vale per
   **tutti** i builder task-scoped: estrazione, giudizio di qualita', revisore di
   conformita', unificazione, entity resolution, reranker, playbook. La chat non
   c'entra — [`agent.py`](../backend/agent.py) passa gia' `reasoning_effort="none"`
   sia all'agente sia al context router. Quindi la spesa di ragionamento e' tutta
   nei compiti di contesto, ed e' proprio dove diversi output sono schemi strict:
   li' lo schema fa il lavoro, non il ragionamento. Un `medium` per sette compiti
   diversi non e' una scelta, e' un default. Misurabile appena c'e' P1.
4. ~~**Gli embedding nel gateway.**~~ Chiuso con t.4: `llm.embed()` ha un ingresso
   suo perche' i token dell'embedding stanno in un altro campo, e leggerli col
   lettore della chat avrebbe dato zero su tutto il volume dell'ingestione.
5. **La trascrizione non e' in nessuna tappa.**
   [`api/routes/audio.py`](../backend/api/routes/audio.py) costruisce un
   `AsyncOpenAI` suo, e `LlmTask.TRANSCRIPTION` con
   `OperationKind.TRANSCRIPTION` esistono gia' nel registro **senza che nessuno
   li usi**. Finche' resta cosi', le ore di audio caricate dai consulenti sono
   spesa invisibile, e P1.6 (la regola L1 in CI) sarebbe rossa. Serve un
   ingresso asincrono nel gateway: e' l'unico punto di chiamata `async` che
   abbiamo, quindi non e' una riga.
6. **Il tenant del registro non e' il consulente.** E' il tenant *workspace*
   (`local` finche' il prodotto e' mono-consulente), non l'id del consulente
   canonical che possiede l'ingestione. Oggi non fa danno - c'e' un consulente
   solo - ma con Track B (identita' per persona) «quanto costa questo cliente»
   ha bisogno che le due cose coincidano, o di una colonna in piu'. Da decidere
   **prima** di P3: i budget per tenant si appoggiano a questo campo.
7. **L'evento di validazione.** Il KPI di punta del piano e' «costo per AS-IS
   validato»: presuppone che la validazione lasci una riga nel database. **Da
   verificare che esista** — se non esiste, quel KPI non e' calcolabile e va
   aggiunto a P1.

---

## ④ Decisioni

### Prese qui, divergono dal piano

**Il retry sul timeout per fonte resta.** Il piano (P0) dice «niente retry su
timeout per le estrazioni lunghe». Non e' stato applicato, e la ragione va
scritta perche' e' una divergenza voluta:
`tests/test_plan_extraction_per_source.py::test_a_source_that_times_out_once_is_read_again`
cita il caso Esaote — un timeout sull'intervista di Francesca, il piano nato su
due voci su tre e dichiarato costruito. Cancellare quel retry regredisce un
incidente reale coperto da un test.

La premessa del piano era «timeout a 60 s anche su interviste di 4.000
caratteri». Con P0.3 quella premessa non c'e' piu': il timeout scala con
l'input, quindi un timeout non e' piu' sfortuna ed e' raro. Il retry per fonte
costa quasi mai, e sopra c'e' comunque la coda con il suo backoff. Se dopo P1 i
numeri dicono che quei secondi tentativi si pagano ancora, si togliera' allora —
con la misura in mano.

**P0.6 rinviato a P2.** «Riferimenti rotti nel piano parziale intercettati prima
del merge» sta in P0 nel piano, ma non e' una leva di spesa: e' qualita'. Ed e'
la parte costosa di P0, quindi tenerla dentro affonda il resto, che si fa in
un'ora. Appartiene a P2, dove i piani parziali diventano artefatti e
l'invalidazione e' il tema.

**Il gateway non nasce da zero.** `backend/llm_config.py` e' gia' il punto di
policy condiviso per 8 degli 11 punti di chiamata. Fuori restano tre:
[`agent.py`](../backend/agent.py) (`DeliRChatOpenAI`),
[`api/routes/audio.py`](../backend/api/routes/audio.py) (trascrizione),
[`memory/embeddings.py`](../backend/memory/embeddings.py) (client `OpenAI` nudo).
P1 estende `llm_config`, non lo sostituisce.

### Aperte, servono a Sohayb

1. **LangSmith (P0.5).** `.env` ha `LANGSMITH_TRACING=true`, e la quota mensile
   e' esaurita dal 6/9: si traccia verso un servizio che rifiuta. Il default nel
   codice e' gia' `False`; e' la configurazione a essere accesa. **Non l'ho
   toccata: `.env` contiene le tue credenziali.** Serve una riga:
   `LANGSMITH_TRACING=false`, oppure un piano a pagamento.
2. **Progetti e chiavi separati (P0.4).** Tre progetti OpenAI — dev, eval, prod
   — con tetto per progetto. Va fatto nel dashboard, non nel codice. Da
   verificare anche se il tetto per progetto e' rigido o solo un avviso.
3. **Fornitore.** Solo OpenAI, o Azure OpenAI UE da subito? Consiglio: **no, non
   ora.** Cambia P1 e non compra niente finche' nessun cliente chiede il DPA.
   Comprala come opzione: `base_url` + stringa modello nel profilo del compito,
   provider-neutrale per costruzione. Costo zero, decisione rimandata senza
   debito.
4. **Chiave admin con `api.usage.read`** per la riconciliazione (L10). Solo lato
   server.

---

## ④bis Lavorare in parallelo su questo piano

### Partire: un comando

```
uv run python scripts/new_agent_worktree.py <nome>
```

Crea il worktree, copia `.env` e `ops/.env`, allinea la porta di Postgres a
quella vera del container, crea `workspace_<nome>`, ci punta
`WORKSPACE_DATABASE_URL` e porta lo schema a head. Da zero a `pytest` verde in
~35 secondi. `--base` per partire da un branch diverso da `main`.

Senza questo si perde un'ora: `.env` e' gitignorato e un worktree nuovo nasce
senza, e un database condiviso si rompe da solo (§⑤).

### Chi fa cosa, senza pestarsi

Le tappe di P1.5 **non sono tutte indipendenti**. Questa tabella dice i file, e
la colonna delle collisioni e' la ragione per cui non si assegnano a caso.

| Tappa | File | In parallelo con |
| --- | --- | --- |
| ~~**t.3** compiti a basso rischio~~ | fatto (reranker, entity resolution) | — |
| ~~**t.3bis** playbook~~ | fatto | — |
| ~~**t.4** embedding~~ | fatto | — |
| ~~**t.5** percorso caldo~~ | fatto | — |
| **t.6** `agent.py` | `agent.py` + **`llm/gateway.py`** (ingresso di streaming) | tutto |
| **eval** operazione `EVAL` | `tests/evals/` | tutto |
| **L5** registro dei prompt | i prompt in tutti i moduli | **dopo t.5**: tocca gli stessi prompt |
| **lettura del registro** | file nuovi (endpoint o SQL versionato) | tutto |
| **P1.6** regola L1 in CI | `.coderabbit/ast-grep-rules/` | **ultima**: prima e' rossa da subito |

Con t.1, t.2, t.3 e t.4 chiusi la collisione su `llm/gateway.py` resta solo per
t.6, che deve aggiungere l'ingresso di streaming: chi la prende lavora da solo
su quel file. Il taglio per due agenti adesso: uno su **t.5** (la piu' grossa),
uno su **t.6 + il test di integrazione del turno di chat**; la lettura del
registro e l'operazione `EVAL` sono file nuovi, quindi vanno con chiunque.

### Le tre regole che evitano i guai visti finora

1. **Un database per worktree.** Lo fa lo script. Non condividere `workspace`.
2. **Chi aggiunge una migrazione Alembic lo scrive subito in §⑥.** E' l'unica
   cosa che rompe le altre sessioni in modo invisibile: applicare una revisione
   che gli altri branch non hanno manda in errore *tutti* i loro test, con un
   messaggio che sembra un bug del codice. E' gia' successo il 2026-09-20.
3. **Non due suite intere insieme.** Contention: la passata di riferimento e'
   passata da ~19 min a 2 h 24, e un test di coda e' fallito solo per quello.
   Durante il lavoro si girano i file toccati; la suite intera una per volta.

### Chiudere un pezzo

Aggiornare §① (cosa e' chiuso, distinguendo *scritto* da *verificato*), §② se il
prossimo passo cambia, §⑥ con la riga di log. Poi merge in `main` con un commit
di merge, che e' la convenzione del repo.

Un pezzo non si dichiara fatto se i suoi test non sono verdi. E la riga di §①
dice **quali** gate sono girati: "verificato" senza dire su cosa non serve a chi
arriva dopo.

## ⑤ Ambiente: cose che fanno perdere un'ora

**Il worktree non ha `.env`.** E' gitignorato, quindi un worktree nuovo nasce
senza. Senza `WORKSPACE_DATABASE_URL` **ogni** test va in errore (non skip):
`tests/conftest.py::_queues_stay_in_the_test_tenant` e' autouse e importa
`workspace_database`. Si copia dal checkout principale, insieme a `ops/.env`.

**La porta di Postgres cambia sotto i piedi.** Windows ha delle
*excluded port range* (qui `55418-55517` e `55530-55629`): la porta 55432 del
compose non si riesce a bindare, `bind: An attempt was made to access a socket in
a way forbidden by its access permissions`. Peggio: il progetto compose si chiama
`ops` da qualunque worktree, quindi **due sessioni che fanno `docker compose up`
si ricreano il container a vicenda** e l'ultima decide la porta. Un run intero
puo' fallire a meta' per questo — e' successo: 1.250 errori che sembravano un
mio bug ed erano il container ricreato sotto. Prima di accusare il codice:

```
docker ps --format '{{.Names}}\t{{.Ports}}'     # la porta vera, adesso
```

e allinea i DSN in `.env`. Al 2026-09-20 la porta e' **55300**.

### Un database per sessione, altrimenti non si lavora in parallelo

Il blocco piu' duro incontrato, e vale la pena spiegarlo per intero perche'
tornera'. Un'altra sessione ha creato la migrazione `0014_notification_reads` nel
suo worktree e l'ha applicata al database `workspace` condiviso. Quella revisione
non esiste in **nessun branch committato**: e' lavoro in corso. Da quel momento
ogni altra sessione trova

```
alembic.script.revision.ResolutionError: No such revision or branch '0014_notification_reads'
```

e **tutti** i suoi test vanno in errore al fixture di sessione. Non e' un bug: e'
una conseguenza. Un solo database + una sola storia Alembic = la prima sessione
che migra chiude fuori le altre, e il danno appare come un guasto del codice
altrui.

La soluzione e' un database per worktree. Il pattern era gia' in uso qui — nel
cluster c'era gia' un `workspace_planfix` — e ora c'e' anche `workspace_p0`:

```
docker exec delir-postgres psql -U delir_super -d delir \
  -c 'CREATE DATABASE workspace_<nome> OWNER delir_workspace;'
```

poi nel `.env` **del proprio worktree** si punta `WORKSPACE_DATABASE_URL` a
`workspace_<nome>`; `_operational_schema` lo porta a head da solo, al primo run.
Il canonical e mem0 restano condivisi finche' nessuno li migra: al 2026-09-20 il
canonical e' a `0017_queue_backoff` in DB e nel branch, quindi allineato. Se
domani un canonical drifta, stessa cura.

Resta comunque la contention: **due suite insieme si rallentano e si disturbano**
(la passata di riferimento e' passata da ~19 min a 2 h 24 con un'altra suite
attiva, e un test di coda e' fallito solo per quello, poi verde da solo). Se un
fallimento non si riproduce da solo, prima di indagarlo guarda se c'era un'altra
suite in corso:

```
Get-Process python | Select-Object Id, CPU, StartTime
```

**I test live si chiedono per nome.** Girano solo con `DELIR_LIVE_LLM=1`, e gli
eval vogliono anche il loro flag:

```
DELIR_LIVE_LLM=1 DELIR_GOLDEN_EVAL=1 uv run pytest tests/evals/test_golden_set.py -q -s
```

Un test nuovo che chiama il provider ha bisogno di due cose, e servono entrambe:
`pytest.mark.live_llm` (la fixture gli lascia la chiave) e il gate di skip (senza
opt-in non gira). Il marker senza il gate paga in CI; il gate senza il marker
trova la chiave a `None` e falla.

---

## ⑥ Log

| Data | Cosa | Dove |
| --- | --- | --- |
| 2026-09-18 | Piano scritto | `docs/llm-gateway-plan.md`, `b483c0e` |
| 2026-09-20 | P0.1 test a opt-in (8 moduli) | `e2b61fe` |
| 2026-09-20 | P0.2 retry in un posto solo, P0.3 timeout proporzionato | `b45b21d` |
| 2026-09-20 | Questo documento | `01be629` |
| 2026-09-20 | 3 moduli che pagavano senza dichiararlo + 2 test allineati alla policy nuova | `chore/llm-spend-p0` |
| 2026-09-20 | `MODEL_MAX_RETRIES` 2 → 0 in `.env` (non committabile), backup `.env.bak-p0` | fuori da git |
| 2026-09-20 | P0 mergiato in main | `7037004` |
| 2026-09-20 | P1.1–P1.4: gateway, operazione, registro dei compiti e dei consumi | `a00179e` |
| 2026-09-24 | P1.5 t.1 + t.3: ingressi che aprono l'operazione, rerank ed entity resolution sul gateway | `d1ea68a`, `chore/llm-t3` |
| 2026-09-24 | P1.5 t.4 + t.3bis: embedding e playbook sul gateway, L2 che non si degrada, e2e della spesa | `chore/llm-t4` |
| 2026-09-24 | P1.5 t.5: percorso caldo sul gateway, cache per fasce di timeout rimossa, segnaposto unico | `chore/llm-t5` |

**Attenzione alla migrazione Alembic.** `0014_llm_usage_ledger` rivede
`0013_conformance_lease`. Un'altra sessione ha creato `0014_notification_reads`
sulla stessa base, sul branch `feat/notifications-feed`: quando entrambe entrano
in main ci saranno **due head** e servira' un `alembic merge`. Non e' un errore di
nessuno dei due, e' il prezzo del lavoro in parallelo — ma va risolto, non
scoperto in produzione.

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

Ultimo aggiornamento: 2026-09-26.
Branch di lavoro: `chore/llm-p2` (worktree `.claude/worktrees/llm-p2`).

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
| P0.6 | Riferimenti rotti nel piano parziale intercettati prima del merge | **fatto, verificato** in P2 (`f2ec891`) |

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
| P1.5 t.6 | `agent.py` (streaming) | **fatto, verificato** |
| P1.5 code | trascrizione (`llm.transcribe`) + operazione `EVAL` | **fatto, verificato** |
| P1.6 | L1 in CI: client del fornitore vietati fuori da `backend/llm/` | **fatto, verificato** (verde su `backend/`, rossa su un file di prova) |
| L5 | Versione del prompt nel registro | **fatto, verificato** (10 punti di chiamata + test AST che impedisce di dimenticarla) |
| Lettura | `llm.ledger` + `scripts/llm_spend.py` | **fatto, verificato** |
| Listino | `LLM_PRICES_JSON` coi prezzi veri | **fatto** (25/09, prezzi sotto). `.env` e' gitignored: su ogni macchina va rimesso |
| Spesa vera | Una riga nata da una chiamata pagata | **fatto, verificato** (25/09: $0.0140, copertura 100%) |

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

**t.6 — la chat, che il gateway costruisce ma non esegue.** E' l'unico compito
di forma diversa: il modello lo fa girare LangGraph, dentro i nodi, e quello che
esce e' uno stream di pezzi verso il frontend. Un `run()` che restituisce il
risultato finale qui non serve a nessuno. Quindi il gateway si divide in due:
`llm.chat_client()` costruisce il client dal profilo del compito, e
`llm.record_streamed_usage()` scrive la riga quando lo stream finisce, dai token
che il runtime **aveva gia' contati** per mandarli al frontend.

Sparisce da `agent.py` tutto il blocco di parametri scritti a mano
(`reasoning_effort="none"`, 512 token per l'instradamento, i retry della chat):
erano le stesse decisioni del registro dei compiti, in un secondo posto e libere
di divergere. `DeliRChatOpenAI` si sposta in `backend/llm/chat_client.py`, che
e' anche quello che serve a L1: una sottoclasse di `ChatOpenAI` e' un client
come gli altri.

**Un turno non e' una voce sola.** Dentro ci gira anche l'instradamento, che ha
un profilo suo. Il runtime somma i token **per nodo** del grafo e scrive una
riga per compito: il nodo dell'instradamento e' `CONTEXT_ROUTING`, tutto il
resto e' `CHAT_TURN`. Sommarli avrebbe dato un totale giusto e due medie
sbagliate, e la prima decisione che si prende col registro in mano e' proprio
quanto far ragionare ciascun compito. Il nome del nodo e' una costante in
`backend/agent.py` che il runtime importa: un rename non puo' far ricadere
l'instradamento dentro il turno in silenzio, e un test costruisce il grafo vero
per verificare che quel nodo esista.

**Quello che ha trovato l'e2e questa volta: i nodi interni non pagavano.** Il
runtime scartava i chunk dei nodi interni **prima** di contarne i token, quindi
l'instradamento — che e' un nodo interno — non compariva da nessuna parte, nemmeno
nel totale mandato al frontend. Quel filtro decide cosa il consulente vede, non
cosa abbiamo pagato: ora il conteggio per il registro avviene prima del filtro, e
`usage_totals` (il numero del frontend) resta quello di sempre, sui soli nodi
visibili. Sono due domande diverse e adesso hanno due conti diversi.

**La regola L2 vale adesso in tutti e quattro i moduli best-effort.** t.3 aveva
risolto il problema cablando gli ingressi; restava che l'`except` largo, se un
ingresso nuovo si dimenticava, avrebbe comunque inghiottito il rifiuto. Adesso
`OperationNotOpen` risale in `reranker`, `entity_resolution` (in **due** punti:
`adjudicate` e il wrapper piu' largo che lo chiama), `memory/embeddings` e
`procedural/extraction`. Un guasto del fornitore degrada come prima; un punto
d'ingresso dimenticato no, perche' non e' un guasto: e' un bug.

**Le due code: la trascrizione e gli eval.** Erano gli ultimi due punti di
chiamata fuori dal gateway, e nessuno dei due e' prodotto nel senso stretto -
uno e' un upload, l'altro e' un test che spende.

La trascrizione ha un ingresso suo, `llm.transcribe()`, perche' e' l'unico punto
`async` che abbiamo; la rotta apre `OperationKind.TRANSCRIPTION` e non costruisce
piu' nessun client. Due cose sono venute fuori solo scrivendolo:

- **il profilo mentiva sul modello.** `profile_for(TRANSCRIPTION).model` tornava
  il modello di *chat*, mentre la trascrizione usa
  `settings.openai_transcription_model`. Il registro avrebbe scritto il nome di
  un modello che non ha mai girato, e il costo stimato sarebbe uscito da un
  listino che non c'entra. Il profilo ora sa dire «il mio modello sta in questo
  setting» (`model_setting`), che e' il gemello configurabile del `model_name`
  fisso dell'embedding;
- **non tutti i modelli di trascrizione fatturano a token.** Whisper si paga al
  minuto di audio e di token non ne dichiara nessuno. La riga si scrive lo
  stesso, con modello ed esito: zero token non vuol dire «gratis», vuol dire
  «non si misura cosi'», e un'ora di audio senza traccia e' spesa invisibile
  come lo erano gli embedding. **Corollario per chi configura:** un modello al
  minuto non va messo in `LLM_PRICES_JSON`, perche' a listino zero token danno
  un costo di zero — plausibile e falso. Fuori listino il costo resta `NULL`,
  che e' la verita': lo sappiamo dalla fattura, non da qui.

Gli eval hanno un `conftest.py` con una fixture autouse che apre
`OperationKind.EVAL`: una per test e non una per sessione, perche' due
esecuzioni dello stesso eval sono due numeri distinti, ed e' cosi' che si vede
se un cambio di prompt ha reso il giudizio piu' caro. `EVAL` esisteva nel
registro da P1.1 senza che lo usasse nessuno. Gli eval veri sono skippati senza
`DELIR_LIVE_LLM=1`, quindi un difetto nel conftest si sarebbe visto solo il
giorno in cui si spende col modello vero: `tests/evals/test_operazione_eval.py`
verifica la fixture senza chiamare nessun modello, e per questo gira sempre.

**P1.6 — la regola L1 in CI, che nasce verde.**
`.coderabbit/ast-grep-rules/python-llm-client-outside-gateway.yml` vieta
`ChatOpenAI`, `AsyncOpenAI`, `OpenAI` e `OpenAIEmbeddings` fuori da
`backend/llm/`. E' `severity: error` e non `warning`: L1 non e' uno stile, e' un
invariante, e una violazione e' un difetto che il codice **oggi non ha**.

Una regola verde va verificata in tutti e due i versi, altrimenti non si sa se
e' verde perche' il codice e' a posto o perche' non matcha niente: verde su
`backend/`, rossa su un file di prova che la viola apposta (tre match, uno per
forma). Il comando documentato nel README della cartella era sbagliato e non
risolveva - il pacchetto e' `ast-grep-cli`, l'eseguibile `ast-grep`:

```
uvx --from ast-grep-cli ast-grep scan --rule .coderabbit/ast-grep-rules/<regola>.yml backend/
```

### La prima spesa vera, e le tre cose che ha detto

Il 25/09 P1 ha smesso di essere verificato solo come codice.
`scripts/llm_spend_e2e_reale.py` fa il percorso del prodotto -
`build_process_understanding` su un'intervista, con giudizio di qualita' - col
modello vero. Due righe nel registro, **$0.0140, copertura 100%**, ciascuna con
la versione del suo prompt; e le versioni sono identiche fra due esecuzioni,
che e' quello che l'hash di un template deve fare.

Il listino e' configurato (`LLM_PRICES_JSON`), prezzi dalla pagina ufficiale
`developers.openai.com/api/docs/pricing` del 25/09, standard tier, dollari per
**milione** di token. `.env` e' gitignored, quindi questi numeri stanno qui o si
perdono:

| modello | input | cached input | output |
| --- | --- | --- | --- |
| `gpt-5.6-luna` | 0.20 | 0.02 | 0.75 |
| `text-embedding-3-small` | 0.02 | — | — |
| `gpt-4o-transcribe-diarize` | **$0.006 / minuto di audio**, non a token: fuori dal listino apposta |

Tre cose che nessun test col confine di rete finto poteva dire:

**1. Una stima a priori sbaglia di un ordine di grandezza.** Stimando i token
dall'intervista (1.244 caratteri, ~311 token) veniva $0.0011. Il registro ne ha
contati **21.386 in ingresso**: dodici volte tanto. L'input non e' la fonte,
sono il prompt di sistema, lo schema di risposta e - per il giudizio di qualita'
- il piano gia' estratto che si rilegge. **Per P3 questo e' un vincolo di
progetto**: una prenotazione di budget calcolata sulla lunghezza dell'input
sarebbe sbagliata di 12x, e va calcolata sul prompt assemblato o su una media
misurata per compito.

**2. L'esperimento su `reasoning_effort` va ripensato.** §③.3 diceva che il
default `medium` su sette compiti e' spreco, e che il primo esperimento e'
abbassarlo. I primi numeri veri dicono altro:

    plan_extraction   effort=medium   ragionamento  2% di 21.838 token di uscita
    plan_quality      effort=low      ragionamento 12% di  3.275 token di uscita

Su `plan_extraction` il ragionamento e' **il 2%**: abbassare l'effort li' non
libererebbe quasi niente, perche' la spesa non e' nel ragionamento - e' nei
21.838 token di **uscita strutturata**, piu' i 21.386 in ingresso. La leva vera
su questo compito e' la dimensione dello schema e del prompt, non l'effort.
L'ipotesi del piano non e' falsa in generale, ma non vale dove pensavamo: va
verificata compito per compito, ed e' proprio a questo che serve il registro.

**3. Il tracing satura e va spento.** Il tenant LangSmith ha superato il limite
mensile di 5.000 tracce: ogni chiamata produce un muro di 429. Non fa cadere il
lavoro, ma rende illeggibile qualsiasi output ed e' latenza pagata per niente.
E' P0.5, che era gia' in attesa, e lo script se lo spegne da solo.

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
`usage.py`, `gateway.py`, `chat_client.py`. `backend/llm_config.py` resta il posto della policy sui
parametri del client e il gateway lo usa — non l'ha sostituito. 36 test in
`tests/test_llm_gateway.py`, ruff e mypy verdi (`backend/llm` e' entrato sotto
mypy).

~~**Finche' P1.5 non e' fatto, il gateway non misura niente in produzione.**~~
Con t.6 P1.5 e' chiusa: ogni punto di chiamata del prodotto passa dal gateway.
Restano fuori solo la trascrizione (§③.5) e gli eval, che non sono prodotto.

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
   fare adesso che P1.5 e' in piedi.

### P2 — Eliminare il lavoro ripetuto

| # | Cosa | Stato |
| --- | --- | --- |
| P2.1 | Impronta del testo sulla fonte, dentro l'identita' del set | **fatto, verificato** (`69d2755`) |
| P2.2 | Piano parziale per fonte come artefatto, `cache_hit` nel registro | **fatto, verificato** (`93ff6ef`) |
| P2.3 | Verdetto del revisore per fonte come artefatto | **fatto, verificato** (`4b553eb`) |
| P2.4 | L9: le risposte del consulente sopravvivono alla ricostruzione | **fatto, verificato** (`8701426`) |
| P2.5 | P0.6: riferimenti rotti corretti sul piano parziale, prima del merge | **fatto, verificato** (`f2ec891`) |
| P2.6 | Eval con record/replay delle estrazioni | **non fatto** — vedi §② |

**Criterio d'uscita del piano, verificato con i test (estrattore sostituito):**
rieseguire sulle stesse fonti non genera estrazioni (`llm_calls == 0`,
`reused == N`); una terza intervista ne genera una. Col modello vero non e'
ancora misurato: va letto nel registro come righe `cache_hit` su
`plan_extraction`.

**P2.1 — l'identita' del set non guardava il testo.** `source_set_identity`
hashava id, nome e scope: diceva *quali* fonti ci sono, non *cosa dicono*.
Un'intervista corretta e risalvata con lo stesso titolo lasciava l'identita'
ferma, il piano passava per aggiornato e descriveva il testo di prima. Ora
`workspace_sources.content_hash` (migrazione `0015`) entra nell'identita'.

Sta in una colonna e non si calcola dal testo per una ragione che va ricordata:
l'identita' si calcola in **due** posti, il registro dell'evidenza (che carica
le trascrizioni) e lo sweep dei piani indietro (che legge i soli record). Se i
due divergessero ogni processo risulterebbe sempre indietro, cioe' una
ricostruzione a ogni passata. Un test li confronta direttamente. La chiave entra
nell'identita' **solo quando c'e'**: le fonti registrate prima non la hanno, e
aggiungerla vuota avrebbe cambiato ogni identita' salvata e mandato in coda la
risintesi di ogni processo. Entrano nel giro al primo salvataggio con impronta.

**P2.2 — la quarta intervista costa una estrazione, non quattro.**
`workspace_plan_extractions` (migrazione `0016`). La chiave e' il testo esatto
che l'estrattore riceve (dentro ci sono gia' i rilievi del revisore, quindi una
riparazione non riusa il parziale che sta correggendo), la versione del prompt
con lo schema, il modello, il ragionamento e il tenant (L8: il tenant e' anche
nel vincolo, per riusare fra clienti bisogna sbagliare due cose). Ogni fonte
riusata lascia una riga `cache_hit` via `llm.record_avoided_call`, che esisteva
da P1 e non la chiamava nessuno. Il riuso e' opt-in (`reuse_artifacts`): lo
chiede `synthesize_process_plan`; i test del merge non ereditano database e
operazione. Magazzino muto = si rilegge e si paga, come prima.

**P2.3 — il revisore di conformita' non leggeva niente, in produzione.** Il
difetto piu' grosso di questo giro, trovato scrivendo la cache e non cercandolo.
`_audit_sources` lancia il revisore in un pool di thread **senza**
`inherit_operation`: da quando il revisore passa dal gateway (t.5) ogni chiamata
partiva senza operazione, il gateway la rifiutava (L2) e l'`except` del pool la
contava come fonte non letta. Il verdetto era `failed`/`incomplete` su ogni
processo, indistinguibile da un fornitore giu'. Nessun test lo vedeva perche' il
revisore finto dei test non passa dal gateway. Ora il pool eredita l'operazione e
`OperationNotOpen` risale; il test usa un revisore finto che si comporta come il
gateway su L2. **Per il prossimo giro:** un doppio che non rispetta L2 non
verifica il cablaggio - e' la stessa lezione di P1 sui doppi piu' permissivi del
vero.

Poi la cache: `workspace_source_audits` (migrazione `0017`), verdetto grezzo
chiavato su fonte come la legge il revisore + elementi del piano. La verifica
delle citazioni si rifa' anche sul verdetto riusato. Niente riuso con `force`:
"controlla di nuovo" vuol dire rileggere. **Guadagno piu' piccolo di P2.2, e va
detto:** un piano cambiato cambia gli elementi, quindi il riuso scatta sui
confronti rifatti a piano fermo (canvas risalvato, verifica ripetuta, fonti
fallite al giro prima).

**P2.4 — L9.** La risposta restava salvata ma si riagganciava solo se il piano
ricostruito riponeva la domanda con lo stesso testo; se l'intervista nuova
spostava l'accento, o un filtro la scartava come ridondante, spariva dal
pannello, dallo snapshot dell'agente e dal gate. Tre test su sei rossi prima del
fix. Ora `prepare_bpmn_review` e `revise_bpmn_review` - i due punti da cui passa
ogni ricostruzione - riportano le domande risposte e le sottraggono ai filtri.
**Limite dichiarato:** la risposta resta e si legge, ma non modifica la
struttura del piano; e una domanda riformulata dal modello puo' essere chiesta di
nuovo accanto a quella risposta.

**P2.5 — P0.6.** I controlli di riferimento escono dalla diagnostica in
`plan_reference_errors` (stessi messaggi, stesso ordine). Sul parziale valgono
solo loro: una voce che non racconta attivita' non e' un piano rotto. Un
parziale con riferimenti rotti si rilegge **una** volta con i punti nominati; la
correzione si verifica con lo stesso controllo e si tiene solo se li riduce;
cio' che resta si dichiara per fonte (`unresolved_references`). La correzione e'
contata in `llm_calls` e finisce nell'artefatto, quindi non si ripaga. Anche qui
`OperationNotOpen` ora risale invece di diventare "fonte persa, ritentata".

### P3–P5

Non iniziati. Vedi il piano.

---

## ② PROSSIMO STEP

**P2 e' chiuso come codice. Il prossimo passo e' misurarlo col modello vero, e
chiudere P2.6.**

**1. Il risparmio nel registro.** Tutto P2 e' verificato con l'estrattore
sostituito. Il gesto: una ricostruzione vera su un processo con tre interviste,
poi una quarta intervista, poi

    uv run python scripts/llm_spend.py ieri

Ci si aspettano righe `cache_hit` su `plan_extraction` pari alle fonti non
cambiate. Se non ci sono, il riuso non scatta in produzione e i test mentono.
Stessa lettura per `conformance_audit` dopo un canvas risalvato: prima di P2.3 li'
non c'era **nessuna** riga `ok`, perche' il revisore non leggeva.

**2. P2.6 — eval con record/replay.** Il criterio del piano: «un eval ripetuto
costa una chiamata». Oggi gli eval passano da `extract_plan_from_sources` senza
`reuse_artifacts`, quindi ripagano tutto. La via piu' corta e' chiedere il riuso
anche dagli eval (l'operazione `EVAL` c'e' gia'), con un tenant dedicato agli eval
cosi' gli artefatti non si mischiano col prodotto. Va deciso se un eval che deve
misurare un **cambio di prompt** lo ottiene gratis - si', perche' il prompt e'
nella chiave - e se ne serve uno che forzi la rilettura.

**Listino e spesa vera (§①, righe di P1).** Sohayb li da' chiusi il 25/09; qui
le righe dicono ancora "da fare/bloccato" perche' la verifica non e' in questo
branch. Le aggiorna chi ha il numero in mano.

**Ancora aperto da P1: il ricalcolo sul database di produzione.** Il listino e'
arrivato dopo le prime righe, e il costo si materializza alla scrittura: tutto
quello che e' girato prima del 25/09 ha `cost_estimate` NULL. Si recupera con

    uv run python scripts/llm_spend.py ricalcola            # prova
    uv run python scripts/llm_spend.py ricalcola --applica

sul database **workspace di produzione**, non su quello di un worktree. Il
tracing dei test invece e' risolto: scrivono su file (`local_tracer`,
[`tracing.md`](tracing.md)), LangSmith resta al prodotto.

**Non ancora P3** (budget con prenotazione e saldo): servono due settimane di
numeri veri, e non e' solo la soglia a dipendere dai dati - la *forma* del
meccanismo lo e'. Prima di P3 va deciso anche il tenant del registro (§③.6), che
e' quello workspace e non il consulente: i budget per tenant si appoggiano a
quel campo. P2 cambia la stima di P3: una sintesi non costa piu' N estrazioni ma
quelle delle fonti cambiate, e il costo atteso va letto dal registro dopo P2,
non da prima.

---

## ③ Cosa manca, in ordine di valore

1. **Registro dei consumi** (P1). Senza, ogni scelta successiva e' a occhio.
2. ~~**Artefatti con dipendenze** (P2, §4.2 del piano).~~ Chiuso come codice
   (§①, P2): impronta per fonte, piano parziale e verdetto del revisore come
   artefatti. Resta da misurarlo col modello vero (§②).
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
5. ~~**La trascrizione non e' in nessuna tappa.**~~ Chiusa con le code di P1.5:
   `llm.transcribe()` e' l'ingresso asincrono, la rotta apre l'operazione, e il
   profilo ha imparato a leggere il proprio modello dai settings invece di
   dichiarare quello di chat.
6. **Il tenant del registro non e' il consulente.** E' il tenant *workspace*
   (`local` finche' il prodotto e' mono-consulente), non l'id del consulente
   canonical che possiede l'ingestione. Oggi non fa danno - c'e' un consulente
   solo - ma con Track B (identita' per persona) «quanto costa questo cliente»
   ha bisogno che le due cose coincidano, o di una colonna in piu'. Da decidere
   **prima** di P3: i budget per tenant si appoggiano a questo campo.
7. ~~**L'evento di validazione.**~~ Verificato il 25/09: **esiste**.
   `approve_bpmn_review` lascia una riga di versione con `status="approved"`,
   che porta `process_id` e `created_at` - tutto quello che serve per attribuire
   la spesa. Il KPI e' calcolabile e si chiede con
   `uv run python scripts/llm_spend.py as-is`. Il costo di un AS-IS e' la spesa
   su quel processo **fino all'approvazione**: quello che viene dopo e'
   manutenzione, e includerlo farebbe crescere il costo di produrre un AS-IS
   ogni volta che si torna su un processo vecchio.

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

**P0.6 rinviato a P2** (chiuso li', §① P2.5). «Riferimenti rotti nel piano parziale intercettati prima
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
| ~~**t.6** `agent.py`~~ | fatto | — |
| ~~**eval** operazione `EVAL`~~ | fatto | — |
| ~~**L5** registro dei prompt~~ | fatto | — |
| ~~**lettura del registro**~~ | fatto (`llm.ledger` + `scripts/llm_spend.py`) | — |
| ~~**P1.6** regola L1 in CI~~ | fatto, e nasce verde | — |

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

## ④ter Lavorare da una PR, senza questa macchina

Questo documento e' scritto per essere letto **anche da chi non ha il portatile
di Sohayb davanti**: un agent nel cloud, o chiunque apra il repo. Vale la pena
dire cosa trova e cosa no, perche' le due liste non sono ovvie.

**C'e', nel repo:** i piani (questo file, `llm-gateway-plan.md`, `tracing.md`),
`CLAUDE.md`, le skill in `.claude/skills/`, la configurazione di CodeRabbit con
le regole ast-grep, tutto il codice e tutti i test. §② dice sempre il prossimo
passo: e' il punto da cui partire, non il piano congelato.

**Non c'e', ed e' voluto:**

- **`.env`.** Contiene chiavi, DSN e il listino. Chi lavora da fuori non lo ha e
  non deve averlo. I **prezzi** pero' servono a leggere il registro, quindi
  stanno in §① di questo file: si ricopiano in `LLM_PRICES_JSON` e bastano;
- **i database.** Postgres e Neo4j girano in container su quella macchina. Da
  una PR non servono: **la CI li ha** (`.github/workflows/ci.yml` li alza come
  servizi), quindi i test veri girano li'. E' la differenza fra «non posso
  verificare» e «verifico aprendo una PR»;
- **la memoria dell'agente.** Vive in `~/.claude/projects/.../memory/`, fuori dal
  repo, e ci resta: il repo e' pubblico e quelle note citano clienti veri. Se un
  fatto serve a chi continua il lavoro, il posto giusto e' questo documento -
  che infatti e' dove sono finiti i numeri veri, le trappole d'ambiente e le
  decisioni.

**Il gesto, da remoto:** branch dal main, commit, push, PR. CI e CodeRabbit
girano sulla PR e dicono se regge; il merge lo decide chi guarda. Quello che
**non** si puo' fare da remoto e' l'ultima verifica di P1 - una chiamata pagata
davvero - perche' vuole una chiave vera: quella resta un gesto su una macchina
con `.env`.

---

## ⑤ Ambiente: cose che fanno perdere un'ora

**Le tracce non vanno su LangSmith quando giri i test, ed e' voluto.** La quota
e' di 5.000 tracce al mese e i test ne avevano bruciate 5.069 in sei giorni,
lasciando il prodotto senza osservabilita' per il resto del mese. Adesso i test
scrivono su file (`data/traces/`) e LangSmith resta al prodotto. Chi cerca «dove
sono finite le mie tracce» trova tutto in [docs/tracing.md](tracing.md),
manopole comprese.


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
| 2026-09-24 | P1.5 t.6: chat e instradamento dal profilo, spesa dello stream nel registro, token dei nodi interni non piu' persi | `chore/llm-t6` |
| 2026-09-24 | Review di t.6: registrazione anche sui turni falliti, modello vero nella riga, tenant dello sweep, listino cachato | `cc9163e` |
| 2026-09-25 | Code di P1.5: trascrizione su `llm.transcribe` (profilo con `model_setting`, righe anche senza token) e operazione `EVAL` negli eval | `chore/llm-code` |
| 2026-09-25 | P1.6: regola ast-grep L1 (`severity: error`), verificata verde su `backend/` e rossa su un file di prova; comando del README corretto | `chore/llm-code` |
| 2026-09-25 | Lettura del registro: `llm.ledger` + `scripts/llm_spend.py`; ogni totale dichiara la sua copertura di prezzo. KPI costo-per-AS-IS calcolabile: l'evento di validazione esisteva gia' | `chore/llm-ledger-read` |
| 2026-09-25 | L5: `prompt_version` su 10 punti di chiamata, hash del template (schema compreso), test AST che impedisce di dimenticarla | `chore/llm-ledger-read` |
| 2026-09-25 | Listino configurato (prezzi ufficiali) e **prima spesa vera nel registro**: $0.0140, copertura 100%. Stima a priori sbagliata di 12x, ragionamento al 2% su plan_extraction | `chore/llm-ledger-read` |
| 2026-09-25 | Tracing diviso: i test scrivono su file (`local_tracer`), LangSmith resta al prodotto. I test avevano bruciato la quota mensile in sei giorni. Ponte spesa-traccia via `operation_id` | `chore/llm-ledger-read` |
| 2026-09-26 | P2.1: impronta del testo sulla fonte, identita' del set che segue il contenuto (migrazione `0015`) | `69d2755` |
| 2026-09-26 | P2.2: piano parziale come artefatto, `cache_hit` nel registro (migrazione `0016`) | `93ff6ef` |
| 2026-09-26 | P2.3: revisore di conformita' che eredita l'operazione (non leggeva in produzione) + verdetto come artefatto (migrazione `0017`) | `4b553eb` |
| 2026-09-26 | P2.4: L9, risposte del consulente riportate a ogni ricostruzione | `8701426` |
| 2026-09-26 | P2.5: P0.6, riferimenti rotti corretti sul piano parziale | `f2ec891` |

**Migrazioni di P2:** `0015_source_content_hash` -> `0016_plan_extraction_artifacts`
-> `0017_source_audit_artifacts`, in fila su `0014_llm_usage_ledger`. Chi ha un
database di worktree fermo a `0014` lo porta a head da solo al primo run.

**Attenzione alla migrazione Alembic.** `0014_llm_usage_ledger` rivede
`0013_conformance_lease`. Un'altra sessione ha creato `0014_notification_reads`
sulla stessa base, sul branch `feat/notifications-feed`: quando entrambe entrano
in main ci saranno **due head** e servira' un `alembic merge`. Non e' un errore di
nessuno dei due, e' il prezzo del lavoro in parallelo — ma va risolto, non
scoperto in produzione.

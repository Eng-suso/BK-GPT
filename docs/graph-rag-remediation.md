# Graph RAG — rimessa a posto del retrieval

Stato: **aperto**. Chiusi GR-01, GR-02, GR-03, GR-12 (branch
`fix/graph-retrieval-budget`) e GR-13 (branch
`fix/process-delete-erases-evidence`, mergiato il 2026-10-02). GR-13 era il
piu' grave dell'elenco e non era un problema di retrieval (§GR-13).
Data apertura: 2026-09-26.

Questo documento non e' una review: e' il piano di lavoro. Ogni voce ha un id
stabile (`GR-xx`) da usare nei nomi di branch e nei commit, il punto esatto nel
codice, lo scenario di guasto concreto, il fix proposto in codice vero, e il
test che lo dimostra. Se un fix non ha un modo di essere dimostrato, il
documento lo dice invece di nasconderlo.

---

## ① Come leggere questo documento

Il cervello e' fatto bene nei confini: il gateway unico in lettura
(`backend/memory/gateway.py`, INV-9) tiene davvero — solo i worker toccano gli
store diretti, verificato; Postgres e' il confine e Neo4j solo una proiezione
con id opachi; il write path ha outbox, dead-letter, backoff con jitter e
savepoint per riga; l'entity resolution rifiuta di fondere su soglia e usa
l'LLM come giudice con apply deterministico.

**GR-01..GR-12 non sono buchi di sicurezza.** Sono problemi di *qualita' e
costo del retrieval*: il grafo risponde meno bene di
quanto potrebbe, a volte lentamente, e — il punto peggiore — **senza dirlo**.
Il codice altrove e' attento proprio a questo ("le risposte sono peggiorate,
niente da guardare"): qui quella cura manca.

### Tabella di marcia

| id | problema | impatto | costo | stato |
| --- | --- | --- | --- | --- |
| GR-01 | nessuna riconciliazione Postgres↔Neo4j (INV-2 dichiarato, mai implementato) | **alto** | 3 h | **fatto** |
| GR-02 | espansione k-hop senza cap: bomba di latenza | **alto** | 2 h | **fatto** (whitelist relazioni: decisione tua) |
| GR-03 | `limit` speso su triple che l'idratazione scartera' | **alto** | 1 h | **fatto** |
| GR-04 | triple non ordinate: il `LIMIT` taglia a caso | medio-alto | 2 h | meta': turni per seed fatti, affinita' con la query no |
| GR-05 | tsvector `'simple'`: zero stemming su corpus italiano | **alto** | 2 h + fork | aperto, serve decisione |
| GR-06 | HNSW post-filtrato: recall che collassa in silenzio | medio | 2 h | aperto |
| GR-07 | seed entita': `LIKE ANY` non usa l'indice trigram | medio | 1 h | aperto |
| GR-08 | nessuna misura di qualita' del retrieval | **blocca 04/05/06** | 3 h + tue 3 h | aperto, serve etichettatura |
| GR-09 | chunking a dimensione: butta i turni di parola | medio | 1 g + backfill | dopo GR-08 |
| GR-10 | nessuna query globale/tematica | funzionale | 2-3 g | dopo GR-08 |
| GR-11 | KG e Mem0 senza arbitro | decisione tua | — | aperto |
| GR-12 | Neo4j senza indici ne' vincoli di unicita' | **alto** | 30 min | **fatto** |
| GR-13 | cancellare un processo non cancella l'evidenza, e lo slug riusato la resuscita | **critico** | decisione + 0,5 g | **fatto** |

"Costo" = mio tempo di implementazione con i test. Non include la tua review.

---

## ② PROSSIMO STEP

1. **GR-13, prima di tutto il resto.** Non e' retrieval, ma e' l'unico punto
   dell'elenco che fa vedere all'utente dati che ha cancellato. Serve una
   decisione di prodotto (§GR-13, "Decisione") prima di scrivere codice.
2. **Riparare i dati dev/pilot** con `scripts/kg_reproject.py --apply` sui
   clienti veri (non sui residui E2E): il confronto sui dati dev ha trovato tre
   famiglie di differenze (§GR-01, "Cosa ha trovato sui dati veri").
3. **GR-05** (serve la decisione del fork multilingua), poi GR-07 e GR-06.

Branch `fix/graph-retrieval-budget`: GR-01, GR-02, GR-03, GR-12, con i test
`tests/test_graph_retrieval_budget.py` (i tre falliscono sul codice prima del
fix) e `tests/test_kg_reproject.py`.

---

## GR-01 — Nessuna riconciliazione Postgres↔Neo4j

### Stato attuale

INV-2 lo dichiara gia': *"Le due code (`graph_outbox`, `mem0_projection_log`)
sono materializzate e ricostruibili"* ([0009_queue_retention.py](../migrations/versions/0009_queue_retention.py)).
La ricostruzione non esiste.

Quello che c'e':

| strumento | cosa fa | cosa non fa |
| --- | --- | --- |
| `GET /observability/queues` ([observability.py:41](../backend/api/routes/observability.py#L41)) | `pending` / `stuck` / `dead_letter` | non dice **da quanto** e' indietro |
| `queue_admin requeue-stuck` | rimette in coda gli `attempts >= 5` | niente per il dead-letter |
| `queue_admin purge-invalid` | sposta i payload non applicabili nel dead-letter | li lascia la' per sempre |
| `neo4j_store.purge_client` | svuota un cliente | non lo ricostruisce |

### Scenario di guasto

1. Un payload finisce in `graph_outbox_dead_letter` (payload non applicabile:
   `InvalidGraphPayload`). Esce dalla coda **intero e con il motivo** — quella
   parte e' fatta bene.
2. Nessuno guarda il dead-letter. Non c'e' allarme, solo un contatore in un
   endpoint.
3. Quell'arco **non esiste in Neo4j**, per sempre. `_expand` non lo attraversa.
4. `graph_retrieve` risponde `status="ok"` con una tripla in meno. Nessun
   segnale. Il sintomo arriva mesi dopo come *"il sistema non si ricorda che
   l'ufficio acquisti passa da Rossi"*.
5. Peggio: la retention **cancella le righe processate** di `graph_outbox`
   (INV-2, per progetto). Quindi **non si puo' ricostruire riproiettando la
   coda**: la riproiezione deve ri-emettere dalle tabelle di dominio.

### Fix

Due pezzi distinti, non confonderli.

**(a) `scripts/kg_reproject.py`** — ricostruisce la proiezione di un cliente
dalle tabelle di dominio Postgres, non dall'outbox.

```
uv run python scripts/kg_reproject.py --client <uuid> --diff      # solo conta
uv run python scripts/kg_reproject.py --client <uuid> --apply     # riproietta
uv run python scripts/kg_reproject.py --client <uuid> --purge-first --apply
```

Implementazione: per ogni tabella in `canonical._TABLES` + `kg_relation` +
gli archi strutturali, ri-emettere il payload `{"kind": "node"|"edge", ...}`
nella forma che `projector.validate_payload` accetta, e applicarlo con
`projector.apply`. `projector` e' **gia'** idempotente (solo `MERGE` /
`DETACH DELETE`, [projector.py:5](../backend/memory/knowledge_graph/projector.py#L5)):
riproiettare due volte non duplica niente. Non serve `--purge-first` tranne che
per togliere nodi orfani (righe cancellate in Postgres mentre il worker era
giu').

`--diff` senza `--apply` e' la modalita' da mettere in CI/cron: conta i nodi e
gli archi attesi vs quelli presenti in Neo4j e stampa la differenza per label.
Uscita non-zero se la differenza non e' zero.

**(b) lag nella risposta del gateway.** `queue_stats` oggi conta le righe
([graph_worker.py:176](../backend/workers/graph_worker.py#L176)) ma non dice
l'eta' della piu' vecchia pendente. Aggiungere:

```sql
SELECT count(*) FILTER (WHERE processed_at IS NULL AND attempts < :m)  AS pending,
       count(*) FILTER (WHERE processed_at IS NULL AND attempts >= :m) AS stuck,
       extract(epoch FROM now() - min(created_at))
         FILTER (WHERE processed_at IS NULL)                           AS oldest_pending_age_s
FROM graph_outbox
```

e in `graph_retrieve`, quando `oldest_pending_age_s` supera una soglia
(`settings.graph_staleness_warn_s`, default 60) o `dead_letter > 0`, aggiungere
al dict di ritorno:

```python
"staleness": {"pending": n, "dead_letter": d, "oldest_pending_age_s": age}
```

e `degradation_counters.bump("graph_retrieve", "stale_projection")`. **La chiave
appare solo quando c'e' qualcosa da dire**: una risposta sana resta identica a
oggi, quindi nessun contratto rotto a valle. Il costo e' una query sulle code
per chiamata: leggerla dal cache TTL 5 s, non ad ogni retrieve.

### Test

- `tests/test_kg_reproject.py`: scrivi entita' + relazione via `canonical`,
  drena la coda, `purge_client`, `--diff` deve contare la differenza esatta,
  `--apply` deve riportarla a zero, un secondo `--apply` non deve cambiare
  niente (idempotenza).
- Un payload nel dead-letter → `graph_retrieve` deve tornare la chiave
  `staleness` con `dead_letter=1`, e il contatore di degradazione deve salire.

### Rischi

`kg_reproject` gira come ruolo con lettura sul dominio + scrittura Neo4j: **non
`delir_worker`** (che ha accesso solo alle code). Usare `delir_migrator` o un
ruolo dedicato, e scriverlo nel docstring — altrimenti qualcuno allarga i grant
del worker per far girare lo script, e il confine dei ruoli salta.

### Fatto (branch `fix/graph-retrieval-budget`)

- `backend/memory/knowledge_graph/reproject.py`: `expected_graph` (cosa il
  write path avrebbe proiettato, guidato da `catalog.NODES` /
  `STRUCTURAL_EDGES`), `diff`, `apply`. Due regole del write path che il
  catalogo non esprime sono replicate con il rimando: props fisse del
  `Process` (`write_process_node`) e il ripiego `affected or [process_id]` per
  gli archi `BLOCKS`/`AFFECTS`.
- `apply` **non svuota il grafo**: toglie solo cio' che avanza (orfani, copie
  duplicate di nodi e di archi) e riapplica tutto con MERGE. Nessuna finestra in
  cui chi legge trova il grafo vuoto — diverso da `--purge-first` proposto
  sopra, che e' stato scartato per questo.
- `scripts/kg_reproject.py --client X [--apply] [--resolve-dead-letter]`.
  Il dead-letter del cliente si cancella **solo se il confronto dopo `--apply`
  e' pulito**, e prima si elenca. Lettura del dominio come `delir_app` via
  `canonical_session` (serve il consulente: RLS), cancellazione del
  dead-letter come `delir_migrator`. Il worker non e' stato toccato nei grant.
- `graph_worker.queue_stats(client_id)` ora ha `oldest_pending_age_s` e il
  filtro per cliente; `graph_retrieve` aggiunge `staleness` **solo** quando il
  grafo di quel cliente e' indietro (dead-letter, bloccate, o pendente piu'
  vecchia di `graph_staleness_warn_seconds`, default 60), con cache per cliente
  di 5 s. Una risposta sana e' identica a prima.
- Test (`tests/test_kg_reproject.py`): il grafo scritto dal write path vero
  confrontato con quello ricostruito risulta identico su tutte le forme (e' il
  test che si rompe se il write path cambia e `reproject` no); ricostruzione
  dopo perdita totale e idempotenza; orfani, archi duplicati e props alla
  deriva rimossi; staleness che compare con un dead-letter e sparisce dopo la
  riparazione.

### Cosa ha trovato sui dati veri

`diff` in sola lettura sui clienti del database dev (9.346 clienti, quasi tutti
residui E2E; il giro e' stato fermato dopo ~600). Tre famiglie, tutte drift
reali e nessuna un errore della ricostruzione — verificato nodo per nodo:

| famiglia | cosa | causa |
| --- | --- | --- |
| Claim alla deriva | nodi `Claim` senza `epistemic_status`, `scope_level`, `quote_verified` | props aggiunte con le migration 0015/0016; i claim proiettati prima non sono mai stati riproiettati. Innocuo oggi (niente le legge in Neo4j), ma e' esattamente il caso "il write path e' cambiato, la proiezione vecchia no" |
| Process mancanti | processi in Postgres senza nodo, e **nessuna** riga pendente o in dead-letter | il nodo `Process` si emette solo dentro `write_evidence`; `scope.resolve` crea la riga `process` senza proiettarla. Un processo senza evidenza non ha nodo, e un arco `AFFECTS`/`BLOCKS` verso di lui crea in Neo4j uno **stub senza `client_id`** |
| Process orfani | nodo `Process` con un `client_id` che non e' quello della riga Postgres | e' GR-13 |

Nodi senza `client_id` in tutto il Neo4j dev: **590** (Process 221, Entity
332, Claim 36, Contradiction 1). Sono invisibili all'espansione (fail closed,
corretto), ma **`purge_client` non li trova** (`MATCH (n {client_id: $cid})`):
l'erasure INV-10 non e' completa. Sono solo UUID, niente PII — ma INV-10 dice
"tutti i nodi". `reproject.apply` ripara quelli agganciati ad archi del
cliente (li riempie con le props del nodo atteso); gli stub completamente
staccati non hanno un cliente a cui ricondurli e serve uno sweep globale
(`MATCH (n) WHERE n.client_id IS NULL AND NOT (n)--() DELETE n`), non ancora
scritto.

---

## GR-02 — Espansione k-hop senza cap

### Stato attuale

[gateway.py:386](../backend/memory/gateway.py#L386):

```cypher
MATCH p = (seed)-[*1..3]-(other)
WHERE (seed.entity_id IN $eids OR seed.process_id = $pid)
  AND all(n IN nodes(p) WHERE n.client_id = $cid)
UNWIND relationships(p) AS r
WITH DISTINCT r, startNode(r) AS a, endNode(r) AS b
RETURN ...
LIMIT $lim
```

Quattro cose in una riga:

1. **variable-length non direzionato** `[*1..3]` senza tipo di relazione: ogni
   arco e' attraversabile in entrambi i sensi;
2. **nessun cap di grado**: un nodo hub moltiplica i path;
3. **`seed.process_id = $pid` su qualunque label**: prende il nodo `Process`,
   che per costruzione e' connesso a tutto il processo → **k-hop da un hub, per
   progetto**;
4. **`LIMIT` dopo `UNWIND ... DISTINCT`**: limita le righe restituite, **non il
   lavoro**. Neo4j enumera i path, li espande in relazioni, deduplica, e solo
   allora taglia.

Fino a 40 seed ([gateway.py:629](../backend/memory/gateway.py#L629)) entrano
tutti insieme in questo `MATCH`.

### Scenario di guasto

Cliente con un processo maturo: 1 nodo `Process`, 300 entita', ~800 relazioni,
grado medio 5, un paio di hub a grado 60 ("Ufficio acquisti", "SAP"). Un
retrieve con `max_hops=2` e il process seed: l'enumerazione dei path passa per
gli hub a ogni hop. Non e' un limite teorico — e' il motivo per cui le query
`[*1..3]` non direzionate sono la prima cosa che si vieta in una code review
Neo4j. In una richiesta di chat sincrona questo diventa un timeout, e
`graph_retrieve` lo restituisce come `status="error"` con lo stacktrace nel
`reason`: l'agente perde il grounding **e non sa perche'**.

### Fix

```cypher
MATCH (seed)
WHERE seed.entity_id IN $eids OR seed.process_id = $pid
CALL {
  WITH seed
  MATCH p = (seed)-[r*1..$hops]-(other)
  WHERE all(n IN nodes(p) WHERE n.client_id = $cid)
    AND all(rel IN r WHERE type(rel) IN $rel_types)
    AND none(n IN nodes(p) WHERE n.degree > $degree_cap)
  RETURN p
  LIMIT $per_seed
}
UNWIND relationships(p) AS rel
WITH DISTINCT rel, startNode(rel) AS a, endNode(rel) AS b
RETURN ...
LIMIT $lim
```

Quattro interventi, in ordine di efficacia:

1. **`LIMIT $per_seed` dentro una subquery `CALL { }` per seed.** E' il
   cambiamento che conta: il lavoro diventa `n_seed × per_seed` invece di
   combinatorio. `per_seed = max(limit // len(seeds), 3)`.
2. **Whitelist dei tipi di relazione.** Le label sono generate da
   `canonical._normalize_relation` ([canonical.py:1203](../backend/memory/knowledge_graph/canonical.py#L1203)),
   quindi l'insieme e' aperto: serve un `SELECT DISTINCT relation FROM
   kg_relation` per sapere cosa esiste davvero, poi una whitelist in
   `settings` con default = tutte le strutturali + le semantiche viste nel
   golden set. **Decisione tua: quali relazioni pesano.** Finche' non c'e', il
   parametro accetta `NULL` = nessun filtro, e i punti 1/3 bastano.
3. **Degree cap.** Serve una proprieta' `degree` materializzata sui nodi (il
   projector la aggiorna a ogni `_merge_edge`), oppure la variante senza
   proprieta': `size([(n)--() | 1]) < $cap` nel `WHERE`, che costa piu' ma non
   richiede migrazione dei dati. Partire dalla seconda.
4. **Separare il seed `Process` dagli altri.** Il nodo processo merita
   `max_hops=1`: da li' a 2 hop si prende mezzo grafo. Due subquery, budget
   diversi.

Nota su `max_hops`: oggi e' clampato `max(1, min(3, ...))` e interpolato in
f-string nel Cypher. Sicuro *perche'* clampato a int, ma e' un pattern che
diventa injection il giorno che il clamp si sposta. ~~Passarlo come parametro
(`$hops`)~~ — non si puo': Cypher non accetta parametri nei limiti di un path
variabile. Fatto invece con una tabella di letterali fissi
(`_HOPS_PATTERN = {1: "*1..1", ...}`): nel testo della query non entra mai un
valore calcolato.

### Test

`tests/test_graph_expansion_budget.py`: costruire in Neo4j un grafo sintetico
con un hub a grado 200 e 40 seed, e asserire (a) che il numero di righe
restituite rispetti il budget, (b) che il tempo di query stia sotto una soglia
generosa (500 ms) — un test di tempo e' fragile, quindi asserire **anche** il
`db.hits` con `PROFILE`, che e' deterministico. Il secondo assert e' quello che
vale; il primo e' la rete di sicurezza.

### Fatto (branch `fix/graph-retrieval-budget`)

`gateway._expand` riscritto (Neo4j 5.26: `CALL (seed) { }` e `COUNT { }`):

- **seed con label** (`(:Entity {entity_id})`, `(:Process {process_id})`): con
  i vincoli di GR-12 sono lookup su indice, prima erano scansioni;
- **budget per seed** in una subquery (`LIMIT $per_seed`, doppio della quota
  giusta, minimo 3) e **uscita a turni**: il primo path di ogni seed, poi il
  secondo... Cosi' il seed con 50 vicini non affama quello con 3 — il test lo
  dimostra: prima il seed piccolo usciva a zero;
- **degree cap** sui nodi intermedi (`graph_expand_degree_cap`, default 100):
  un hub come estremo si', come passaggio no;
- `truncated` nella risposta quando il budget ha tagliato.

Scelte diverse dal piano, e perche':

- **Il seed `Process` non e' stato limitato a 1 hop.** A 2 hop dal processo ci
  sono le contraddizioni fra i suoi claim (`Process→Claim←BETWEEN–Contradiction`):
  toglierle senza GR-08 per misurare era una regressione alla cieca. Il budget
  per seed basta a togliere il costo dell'hub.
- **La whitelist dei tipi di relazione non c'e'.** E' una decisione di dominio
  (quali relazioni pesano), non tecnica. Il cap per seed e il degree cap sono
  la parte che conta per la latenza.

La misura con `PROFILE`/`db.hits` proposta sopra non e' stata scritta: i test
asseriscono le proprieta' (budget rispettato, equita', hub non attraversato),
non i tempi.

---

## GR-03 — Il `limit` si spende su triple che verranno scartate

### Stato attuale

`_expand` riceve `client_id`, **non lo scope**
([gateway.py:371](../backend/memory/gateway.py#L371), chiamata a
[:638](../backend/memory/gateway.py#L638)):

```python
triples = _expand(client_id, seeds, process_id, max_hops, limit)
matches = _hydrate(consultant_id, scope, triples, authorized_sources) if triples else []
```

L'espansione e' **client-wide**. Il confine di processo/progetto viene
riapplicato solo in `_hydrate` ([gateway.py:493](../backend/memory/gateway.py#L493)),
che scarta fail-closed ogni tripla con un estremo fuori scope o non idratabile.

**Questo e' corretto come sicurezza** — Postgres e' il confine, e il commento
spiega bene perche' (INV-9, test E2E V2). Ma il budget e' speso prima del
filtro.

### Scenario di guasto

Cliente con 6 processi mappati, retrieve scoped sul processo #3 con
`limit=25`. Neo4j restituisce 25 triple prese da tutto il cliente; l'idratazione
ne scarta 20 perche' appartengono ai processi #1, #2, #4-#6. L'agente riceve
**5 triple** e uno `status="ok"`. Le triple in-scope che esistevano erano 18:
13 non sono mai state lette. Nessun segnale: `count` dice 5 e sembra che il
grafo sappia poco di quel processo.

Il difetto peggiora con il numero di processi per cliente — cioe' peggiora
**quanto piu' il prodotto viene usato**.

### Fix

Pre-filtrare in Neo4j con gli stessi id che l'idratazione usera' comunque, e
tenere l'idratazione come rete di sicurezza (non toccarla: e' il confine).

`_expand` prende `scope` e `authorized_sources`, e il `WHERE` diventa:

```cypher
AND all(n IN nodes(p) WHERE n.client_id = $cid
        AND (n.process_id = $scope_pid OR n.project_id = $scope_prj
             OR any(s IN n.source_ids WHERE s IN $sids)))
```

Perche' funzioni servono `project_id` e `source_ids` **sui nodi proiettati**.
Da verificare in `canonical._emit_node` / `projector`: se oggi il nodo porta
solo `client_id`, e' una modifica del write path + riproiezione (→ dipende da
GR-01, che e' nello stesso branch: bene).

**Variante senza toccare il write path** (da fare prima, se la proiezione non
porta gli id): sovra-campionare e tagliare dopo l'idratazione —
`_expand(..., limit=limit * over)` con `over = 4`, poi `matches[:limit]`. E'
una pezza, non un fix: sposta il costo su Neo4j invece di risolverlo, e con 20
processi per cliente `over=4` non basta. Va scritto nel codice che e' una
pezza, con il link a questo paragrafo.

In entrambi i casi: se `len(triples) == limit` (budget saturo) **e** dopo
l'idratazione `len(matches) < limit`, aggiungere `"truncated": True` alla
risposta. E' l'informazione che oggi manca completamente.

### Test

`tests/test_graph_scope_budget.py`: un cliente, 4 processi, 40 triple per
processo, retrieve scoped su uno con `limit=25` → asserire `len(matches) == 25`
e che tutte siano del processo giusto. Oggi questo test **fallisce**: e' la
dimostrazione del difetto, da scrivere prima del fix.

### Fatto (branch `fix/graph-retrieval-budget`) — con un approccio diverso

Verificando il write path e' venuto fuori che i nodi proiettati portano
`client_id` e `project_id`, **ma non `process_id` ne' `source_ids`** (le entita'
sono condivise fra processi per progetto). Il pre-filtro proposto sopra
avrebbe richiesto di cambiare il write path e riproiettare tutto.

Fatto invece: `_in_scope_node_ids` calcola **in Postgres** l'insieme esatto
degli id leggibili — un sovrainsieme largo per SQL, poi deciso da
`_Node.in_scope`, **la stessa funzione dell'idratazione** — e lo passa a Neo4j,
che non enumera path attraverso nodi fuori da quell'insieme. Una sola regola,
scritta in un posto; zero cambi al write path; nessuna riproiezione.
`_hydrate` resta intatta ed e' ancora il confine.

Il test scritto prima del fix (30 vicini nel processo B, 10 nel processo A,
lettura scoped su A con `limit=10`) sul codice vecchio tornava **0 triple e
`status: empty`** — peggio di quanto stimato sopra. Ora ne torna 10, tutte di
A. La suite di isolamento esistente (`test_process_evidence_isolation`,
`test_evidence_scope`, provenance E2E, 103 test) e' verde: il confine non e'
cambiato.

---

## GR-04 — Le triple tornano non ordinate

### Stato attuale

RRF (`_rrf`, [gateway.py:180](../backend/memory/gateway.py#L180)) e' usato bene
due volte: sui chunk (lessicale + vettoriale) e sui seed (nomi + provenance).
Poi si ferma. Le triple espanse **non vengono mai scorate contro la query**:
l'ordine e' quello con cui Neo4j enumera i path, e il `LIMIT` taglia a quel
punto.

`relation_focus` ([gateway.py:648](../backend/memory/gateway.py#L648)) fa un
sort stabile che porta avanti le relazioni che contengono il focus — **dopo** il
taglio. Se la relazione cercata e' stata tagliata dal `LIMIT`, il focus non fa
niente.

### Scenario di guasto

Query: *"chi approva le fatture sopra i 5.000 euro"*. L'espansione restituisce
25 triple ordinate come capita; la tripla `Responsabile acquisti -[APPROVA]->
Fattura oltre soglia` e' la 31esima nell'enumerazione di Neo4j. Non arriva.
L'agente risponde senza, o chiede una cosa che il grafo sapeva.

### Fix

Servono due segnali che ci sono gia' e uno nuovo:

1. **distanza dal seed** (hop): la tripla a 1 hop da un seed forte vale piu' di
   quella a 3 hop. Restituire `length(p)` dal Cypher.
2. **rank del seed**: i seed arrivano gia' ordinati da RRF
   ([gateway.py:626](../backend/memory/gateway.py#L626)) — conservare il
   punteggio invece di scartarlo (`[eid for eid, _ in ...]` butta via lo score).
3. **affinita' testuale della tripla con la query**: il testo idratato
   (`source`/`relation`/`target`) contro i termini della query. Overlap
   lessicale, non un embedding: qui un embedding per tripla e' costo di rete
   sul path di grounding.

Poi RRF su queste tre liste, e il taglio a `limit` **dopo** l'ordinamento e
**dopo** l'idratazione. `relation_focus` diventa un boost nel punteggio, non un
sort finale.

Il `score` va nel dict del match, come e' stato fatto per i chunk
(`ChunkHit.as_dict` espone `score`, `lexical_score`, `vector_score`): la
stessa onesta' — chi legge vede perche' una tripla e' arrivata.

### Test

L'ordinamento relativo si testa in modo deterministico (un grafo dove la
risposta e' a 1 hop e il rumore a 3 → la risposta e' prima). Ma **se
l'ordinamento migliora le risposte vere** si misura solo con GR-08. Quindi:
GR-04 si implementa e si testa per costruzione, e si *valida* dopo.

### Stato

Meta' fatta dentro GR-02: le triple escono **a turni per seed, nell'ordine di
rank RRF dei seed**, prima del `LIMIT` — il taglio non e' piu' arbitrario fra
seed. Resta aperto il segnale 3 (affinita' testuale della tripla con la query) e
il `score` esposto nel match; `relation_focus` e' ancora un sort dopo il taglio.

---

## GR-05 — tsvector `'simple'`: zero stemming

### Stato attuale

Colonna generata ([0002_sources_chunks.py:68](../migrations/versions/0002_sources_chunks.py#L68)):

```sql
content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
```

Lato query ([gateway.py:275](../backend/memory/gateway.py#L275)):

```sql
FROM kg_chunk, to_tsquery('simple', :tsq) AS q
WHERE client_id = :cl AND content_tsv @@ q
```

`'simple'` = **nessuno stemming, nessuna stopword**. Su corpus italiano:

| query | documento | match oggi |
| --- | --- | --- |
| fatture | "la fattura passa da..." | ❌ |
| approvazione | "chi approva e' il..." | ❌ |
| pagamenti | "il pagamento parte..." | ❌ |
| perche' | "perché il flusso..." | ❌ (nessun `unaccent`) |

Meta' del recall lessicale del retrieval ibrido, buttata. E siccome l'altra
gamba (vettoriale) si spegne senza `OPENAI_API_KEY`, in configurazione
degradata il retrieval lessicale e' **tutto** quello che c'e'.

Nota: il docstring di `_text_search` dice `websearch_to_tsquery`
([gateway.py:19](../backend/memory/gateway.py#L19)) ma il codice fa
`to_tsquery` con OR-of-terms. Documentazione alla deriva, da allineare
nello stesso commit.

### Fork — serve una tua decisione

Il prodotto e' multilingua (i18n chiuso in U4: la lingua scelta vale in tutto
il prodotto). Le fonti di un cliente possono essere in italiano, e domani in
inglese. Tre strade:

| | come | pro | contro |
| --- | --- | --- | --- |
| **A. `'italian'` fisso** | cambio la config della colonna generata | 1 migration, semplice | su fonti inglesi lo stemmer italiano peggiora le cose |
| **B. colonna `language` su `kg_source`** | tsvector generato con `regconfig` per riga | corretto | `GENERATED ALWAYS` non puo' dipendere da un'altra tabella → serve `language` su `kg_chunk`, popolata alla scrittura, + trigger o colonna non generata |
| **C. due tsvector** (`tsv_it`, `tsv_en`) | `@@` su entrambe, RRF | nessuna scelta a monte | raddoppia indice e spazio |

**Raccomandazione: A adesso, B quando arriva il primo cliente non italiano.**
Il pilot e' italiano; C e' costo senza domanda. Ma A va scritta con la nota che
il giorno del cliente inglese serve B, altrimenti diventa un difetto silenzioso
identico a questo.

### Fix (strada A)

Non e' una riga. `content_tsv` e' `GENERATED ALWAYS`: la config non si cambia
con un `ALTER`. Migration:

```sql
DROP INDEX kg_chunk_tsv;
ALTER TABLE kg_chunk DROP COLUMN content_tsv;
ALTER TABLE kg_chunk ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('italian', content)) STORED;
CREATE INDEX kg_chunk_tsv ON kg_chunk USING gin (content_tsv);
```

Riscrittura della tabella + ricostruzione dell'indice: su un DB da pilot sono
secondi, ma va sotto `ACCESS EXCLUSIVE`. Da mettere nella finestra di
migrazione, non a caldo.

Lato query, `to_tsquery('simple', " | ".join(terms))` diventa
`websearch_to_tsquery('italian', query)` — che e' quello che il docstring dice
gia' — cosi' lo stemming si applica **su entrambi i lati** (obbligatorio: query
e documento devono usare la stessa config) e la sintassi utente (frasi tra
virgolette, `-esclusione`) viene gestita da Postgres invece che dal regex
`_WORD`. Attenzione: `websearch_to_tsquery` mette gli `&` (AND) dove oggi c'e'
`|` (OR) → il recall cambia natura. Da valutare: `websearch_to_tsquery` per la
precisione **piu'** una seconda query OR-of-terms per il recall, fuse con RRF.
E' la stessa filosofia dei due segnali esistenti, ed e' il modo di non
scambiare un difetto con un altro.

Accenti: `CREATE EXTENSION unaccent` (il bootstrap crea gia' `pg_trgm`, quindi
il posto c'e': [ops/postgres/init/00-bootstrap.sh](../ops/postgres/init/00-bootstrap.sh))
e config custom `italian_unaccent`. Facoltativo, ma su nomi propri e "perche'"
si sente.

### Test

`tests/test_kg_lexical_stemming.py`: un chunk con "la fattura passa dall'ufficio
acquisti", query "fatture" → deve matchare. Oggi fallisce. Piu' i tre casi
della tabella sopra.

---

## GR-06 — HNSW post-filtrato: recall che collassa in silenzio

### Stato attuale

Indice ([0002_sources_chunks.py:84](../migrations/versions/0002_sources_chunks.py#L84)):

```sql
CREATE INDEX kg_chunk_hnsw ON kg_chunk USING hnsw (embedding vector_cosine_ops);
```

Query ([gateway.py:290](../backend/memory/gateway.py#L290)):

```sql
SELECT ... FROM kg_chunk
WHERE client_id = :cl AND embedding IS NOT NULL
  AND source_id = ANY(CAST(:sids AS uuid[]))     -- molto selettivo
ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k
```

pgvector con HNSW **filtra dopo** la ricerca nell'indice: percorre il grafo
HNSW raccogliendo `ef_search` candidati (default **40**), poi applica il
`WHERE`. Con un filtro selettivo — ed `source_id = ANY(...)` sulle sole fonti
autorizzate di *un processo* lo e' molto — i candidati sopravvissuti possono
essere pochi o zero, e Postgres restituisce **meno di `k`** vicini, o il
planner cade in seq scan (che e' lento ma corretto).

Nessun `SET hnsw.ef_search`, nessun indice parziale per scope. Da notare che la
0011 ha fatto la cosa giusta su `kg_entity` (indice **parziale** su `embedding
IS NOT NULL`), e su `kg_chunk` no.

### Scenario di guasto

Cliente con 8.000 chunk su 6 processi. Retrieve scoped: le fonti autorizzate
sono 200 chunk (2,5%). `ef_search=40` → dei 40 candidati raccolti, in media 1
appartiene allo scope. `k=8` richiesti, 1 restituito. La gamba vettoriale del
retrieval ibrido **e' spenta di fatto**, e l'RRF fonde un segnale vuoto con
uno. Nessun errore, nessun log: solo risposte peggiori.

La sicurezza tiene (il filtro c'e' e funziona). E' il recall che muore.

### Fix

Tre mosse, dalla piu' economica:

1. **`SET LOCAL hnsw.ef_search = 200`** nella transazione della query
   vettoriale. Costo: latenza per candidato, lineare. Mitiga, non risolve.
2. **Indice parziale** `WHERE embedding IS NOT NULL` (allineandolo a
   `kg_entity`): non aiuta la selettivita' di scope ma toglie dall'indice le
   righe non ancora embeddate — che sono tante appena arriva una fonte nuova.
3. **Il fix vero: pre-filtrare invece di post-filtrare.** Quando le fonti
   autorizzate sono poche, un seq scan *sui soli chunk autorizzati* batte
   l'indice. Due strade:
   - `ORDER BY` su una CTE materializzata dei chunk autorizzati (il planner
     abbandona HNSW e fa una distanza esatta su 200 righe: **piu' preciso e
     piu' veloce** del post-filtro);
   - scegliere in base alla cardinalita': `if len(source_ids) * stima_chunk <
     soglia: esatto; else: HNSW + ef_search`.

   La prima e' preferibile: meno codice, risultato esatto. La distanza esatta su
   poche centinaia di vettori a 1536 dimensioni e' dell'ordine dei
   millisecondi.

### Test

`tests/test_kg_vector_recall_under_filter.py`: 5.000 chunk, 100 in scope,
query il cui vicino piu' prossimo **in scope** e' noto per costruzione →
asserire che venga restituito. Oggi, con `ef_search` default, questo test
fallisce in modo probabilistico (quindi: seed fisso sui vettori sintetici, non
random). Piu' un confronto contro il risultato esatto (`ORDER BY` senza indice,
`SET enable_indexscan = off`): il recall@k misurato deve essere 1.0.

Questo e' l'unico dei fix di recall che **si dimostra senza GR-08**, perche' la
verita' e' calcolabile (il vicino esatto), non giudicata.

---

## GR-07 — `LIKE ANY` non usa l'indice trigram

### Stato attuale

La 0011 crea `kg_entity_name_trgm` GIN trigram su `lower(canonical_name)`
([0011:47](../migrations/versions/0011_entity_resolution_indexes.py#L47)).
Il seed dell'entita' fa ([gateway.py:166](../backend/memory/gateway.py#L166)):

```sql
OR lower(canonical_name) LIKE ANY(:like)     -- ['%fattura%', '%ufficio%', ...]
```

`LIKE ANY(array)` e' uno ScalarArrayOp: **l'indice trigram non e' utilizzabile
dal planner** in questa forma (il GIN trgm serve `LIKE` con pattern costante).
Risultato atteso: seq scan su `kg_entity` a ogni retrieve, con un pattern per
ogni parola ≥3 caratteri della query.

**Da verificare prima di toccare** — se il planner nelle nostre versioni fa
qualcosa di piu' furbo, il fix e' inutile:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM kg_entity
WHERE client_id = '<uuid>' AND status = 'active'
  AND lower(canonical_name) LIKE ANY(ARRAY['%fattur%','%ufficio%','%acquist%']);
```

Cercare `Seq Scan on kg_entity` vs `Bitmap Index Scan on kg_entity_name_trgm`.

### Fix

Se confermato, riscrivere come OR di `LIKE` con pattern parametrici distinti
(indicizzabile), oppure usare l'operatore di similarita' trigram — che e' quello
per cui l'indice e' stato creato:

```sql
OR EXISTS (SELECT 1 FROM unnest(:terms) t
           WHERE lower(canonical_name) % t)     -- pg_trgm similarity, usa il GIN
```

`%` usa `pg_trgm.similarity_threshold` e da' anche una **tolleranza ai typo**
che `LIKE '%x%'` non ha. Coerente con il livello 1 dell'entity resolution, che
usa gia' trigram per il recall — con la stessa avvertenza scritta la': il
trigram **propone**, non decide.

Impatto secondario: con molte parole nella query il `LIMIT 40` sui seed viene
saturato da entita' con nomi lunghi che contengono una parola comune. L'ORDER BY
attuale (esatto prima, poi nome piu' corto) e' una scelta ragionata e va
lasciata; il punto e' solo non pagare un seq scan per arrivarci.

---

## GR-08 — Non esiste una misura della qualita' del retrieval

### Stato attuale

Il golden set esiste e **e' fatto bene**, ma misura un'altra cosa:

| misura | dove | cosa copre |
| --- | --- | --- |
| piano → disegno | `tests/test_golden_graph_metrics.py` | compilatore BPMN, deterministico, ogni CI |
| interviste → piano | `tests/evals/test_golden_set.py` | estrattore LLM, notturno |
| **query → contesto** | **niente** | **il retrieval** |

`tests/test_kg_vector_retrieval.py` e' un test funzionale (il vettoriale gira e
torna qualcosa), non una metrica.

Conseguenza diretta: **GR-04, GR-05 e GR-09 non sono dimostrabili oggi.** Posso
scriverli, posso testarli per costruzione, ma non posso dire "il retrieval e'
migliorato del X%". E senza quel numero, la prossima modifica al retrieval puo'
regredire senza che nessuno se ne accorga — che e' precisamente il problema di
GR-01 spostato di un livello.

### Fix

`tests/evals/retrieval/` con lo stesso spirito del golden set esistente
(deterministico dove puo' esserlo, difensivo dove non puo'):

```
tests/evals/retrieval/
  cases.json          query → chunk/entita' attesi, per caso golden
  test_retrieval_eval.py
```

Metriche: **recall@k** e **MRR** sui chunk, recall sulle entita' seed. Niente
giudice LLM: un eval giudicato da un LLM misura l'accordo fra due LLM — e' la
frase che sta gia' in `tests/evals/graph_metrics.py`, e vale qui identica.

Le fonti ci sono: `tests/golden/esaote_ciclo_passivo/sources/` e
`tests/golden/facility_segnalazioni_guasti/sources/`.

### Questo e' il blocco, e non lo sblocco io

Servono **30-50 query etichettate** con i passaggi attesi. Non le genero io: se
scrivo io le query e le risposte attese, misuro me stesso — l'eval direbbe solo
che il retrieval trova quello che ho deciso dovesse trovare.

Le scrivi tu, dalle fonti che ci sono gia', ~2-3 h. La forma e' minima:

```json
{"query": "chi approva le fatture sopra soglia",
 "case": "esaote_ciclo_passivo",
 "expect_chunks": ["<source_id>:<ordinal>", "..."],
 "expect_entities": ["Responsabile acquisti"]}
```

Le query utili sono quelle che un consulente farebbe davvero, incluse le
brutte: sinonimi non presenti nel testo, morfologia diversa (e' il caso che
smaschera GR-05), domande di relazione (GR-04), domande su un processo mentre
lo scope e' su un altro (GR-03).

Una volta che il file esiste: harness ~3 h mie, poi i numeri prima/dopo di ogni
fix diventano automatici, e GR-09/GR-10 smettono di essere scommesse.

---

## GR-09 — Chunking a dimensione butta i turni di parola

### Stato attuale

[canonical.py:762](../backend/memory/knowledge_graph/canonical.py#L762):

```python
_CHUNK_CHARS = 1600
_CHUNK_OVERLAP = 200
```

`_chunk_text` normalizza il whitespace (`" ".join(content.split())`) e taglia
greedy a 1600 caratteri, cercando un confine di frase o parola nella seconda
meta'. E' un chunker onesto e ben scritto per prosa continua.

Il problema e' cosa ci passa dentro: **interviste**. La normalizzazione del
whitespace cancella i cambi di riga, quindi i turni di parola ("*Rossi:* ...
*Bianchi:* ...") diventano un flusso unico, e un chunk contiene meta' di una
risposta di Rossi e meta' di una di Bianchi.

Questo e' in tensione diretta con un invariante del sistema: i claim portano
`attributed_to` e `source_name` perche' *"un claim che arriva nel contesto senza
la sua voce e' materiale per una misattribuzione"*
([gateway.py:556](../backend/memory/gateway.py#L556)) — e nel V3 e' successo
davvero. Ma il chunk che alimenta l'estrazione ha gia' perso il confine di chi
parla.

### Fix

Chunker che conosce la struttura: turni di parola (`^\s*([A-Z][\w .'-]{1,40}):`),
titoli di sezione, elenchi. Un chunk non attraversa un cambio di parlante; se un
turno supera `_CHUNK_CHARS` si spezza dentro il turno, ripetendo l'etichetta del
parlante in testa al chunk successivo. Il parlante diventa un campo di
`kg_chunk`, non solo testo.

### Costo nascosto: reindicizzazione

Cambiare il chunker **invalida tutti gli embedding esistenti** di `kg_chunk`:
gli `ordinal` cambiano, i confini cambiano. Serve:

- `EMBED_VERSION = 1` → `2` ([embeddings.py](../backend/memory/embeddings.py)).
  **Il contratto lo prevede gia'**: `kg_chunk.embed_version` esiste dalla 0002.
  Questa e' la prova che la scelta di versionare l'embedding era giusta — si usa
  qui, la prima volta.
- script di re-chunk + re-embed per fonte, con `embed_version < 2` come
  selettore, idempotente e riprendibile.
- costo in denaro: trascurabile con `text-embedding-3-small`
  (~$0.02 per milione di token). Il costo e' il tempo, non i soldi.

Da fare **dopo GR-08**, non prima: e' la modifica di cui e' piu' facile
convincersi a torto.

---

## GR-10 — Nessuna query globale o tematica

### Stato attuale

`graph_retrieve` e' local search: seed → k-hop → idratazione. Risponde bene a
*"chi approva le fatture"*. Non ha nessun path per:

- *"quali sono i temi ricorrenti nei processi di questo cliente"*
- *"dove si concentrano le inefficienze"*
- *"cosa hanno in comune i tre processi che ho mappato"*

Non e' un difetto di implementazione: **manca il secondo modo di interrogare**.
Nella letteratura GraphRAG e' la distinzione local/global search, e la global
richiede struttura che non abbiamo: community detection sul grafo + riassunti
gerarchici per comunita', generati in ingestione e interrogati in lettura.

Per un prodotto di consulenza di processo questo e' un buco **funzionale**, non
una rifinitura: "dimmi cosa vedi in questo cliente" e' letteralmente il mestiere.

### Fix (abbozzo, da pianificare a parte)

1. community detection su Neo4j (Louvain/Leiden — serve GDS, che nella
   Community edition **non c'e'**: alternativa, calcolarla in Python su un dump
   del sottografo del cliente, con `networkx`, in un worker);
2. per comunita', un riassunto LLM scritto in Postgres (`kg_community`,
   `kg_community_summary`) con provenance e scope come tutto il resto;
3. ricalcolo incrementale in `kg_ingest_queue` quando il grafo del cliente
   cambia oltre una soglia;
4. `graph_retrieve_global(query)` nel gateway: RRF sui riassunti di comunita' →
   espansione locale sui seed delle comunita' vincenti.

2-3 giornate, e va **pianificato come feature** (P-qualcosa nel workstream KG),
non infilato in un branch di fix. Dipende da GR-08 per sapere se aiuta.

---

## GR-11 — KG e Mem0 senza arbitro

### Stato attuale

Due memorie alimentano il contesto dell'agente:

| | store | governo dei conflitti |
| --- | --- | --- |
| KG | Postgres + Neo4j | `kg_contradiction`, con `divergence_type` e la distinzione `incompatible` vs il resto — **fatta bene** |
| Mem0 | pgvector isolato | nessuno |

`gateway.memory_search` post-filtra per `client_id` sui metadata (sicurezza, ok)
ma niente riconcilia un fatto Mem0 con un `kg_claim` che lo contraddice, e
niente deduplica un fatto presente in entrambi.

### Scenario

Mem0 ricorda *"il cliente approva tutto via email"* (detto in un incontro di
tre mesi fa). `kg_claim` dice *"l'approvazione passa dal portale"* con
`attributed_to` e quote verificata. Entrambi entrano nel contesto. L'agente
scegliera' per conto suo — e siccome Mem0 non porta ne' provenance verificabile
ne' data di riferimento nella stessa forma, non ha nemmeno gli elementi per
scegliere bene.

### Non e' una stima, e' una decisione tua

Le opzioni si escludono:

- **il KG vince sempre** quando i topic collidono (Mem0 resta per le
  preferenze del consulente, non per i fatti del cliente) — semplice, e
  probabilmente giusto: il KG ha provenance, Mem0 no;
- **arbitrato esplicito**: i fatti Mem0 client-scoped diventano `kg_claim` a
  bassa confidenza, e il macchinario di contraddizione esistente li gestisce —
  coerente, piu' lavoro;
- **separazione per dominio**: Mem0 solo consultant-level (mai fatti di
  cliente), imposto in scrittura — il piu' pulito, ma potrebbe togliere roba
  che oggi serve.

Non la decido io. Va deciso prima di GR-10, perche' i riassunti di comunita'
peggiorerebbero il problema (una terza voce senza arbitro).

---

## GR-12 — Neo4j senza indici ne' vincoli di unicita' — fatto

Trovato scrivendo GR-02: `SHOW INDEXES` sul Neo4j dev restituiva solo i due
indici `LOOKUP` di default. Nessun indice di proprieta', nessun vincolo. Quindi:

- ogni `MERGE (n:Entity {entity_id: $id})` del projector era una scansione di
  tutti i nodi `Entity` (52.174 nodi nel dev);
- ogni lookup di seed in `_expand` idem;
- due `MERGE` concorrenti sullo stesso id potevano creare due nodi — oggi il
  worker e' singolo, ma e' l'unica cosa che lo impediva.

`neo4j_store.ensure_schema()`: un vincolo `IS UNIQUE` per ogni `(label, id)` di
`catalog.NODES` (il vincolo porta l'indice), `IF NOT EXISTS`, una volta per
processo, chiamato da `graph_worker.drain_once` e da `reproject.apply`. Se
fallisce — tipico: duplicati gia' presenti — lo scrive a livello ERROR e lascia
girare la proiezione: senza indice e' lenta, non sbagliata; i duplicati si
tolgono con `kg_reproject --apply`. Sul dev i vincoli si sono creati: nessun
duplicato.

---

## GR-13 — Cancellare un processo non cancella l'evidenza, e lo slug riusato la resuscita

**Stato: fatto (2026-10-02).** Presa l'opzione (a) della decisione 1:
cancellare un processo, un progetto o un cliente cancella la sua evidenza
(`knowledge_graph/erase.py`, chiamato da `delete_process` / `delete_project` /
`delete_client` prima del workspace). La decisione 2 e' coperta in parte:
`scope._upsert` stacca dallo slug la riga canonical di un altro progetto, e
`erase_process` non cancella niente se lo slug porta al processo di un altro
progetto. Prove: `tests/test_process_delete_erases_evidence.py`.

**Non e' un problema di retrieval, ed e' il piu' grave dell'elenco.** Trovato
perche' `kg_reproject` ha segnalato un nodo `Process` orfano: il nodo in Neo4j
diceva cliente `9e16…`, la riga Postgres cliente `717d…`.

### Il meccanismo

Tre pezzi, ognuno ragionevole da solo:

1. `workspace_database.delete_process` ([workspace_database.py:2953](../backend/workspace_database.py#L2953))
   cancella la riga workspace, il modello BPMN, fonti e decisioni. **Non tocca
   il canonical**: la riga `process`, le `kg_entity`/`kg_claim`/`kg_source`/
   `kg_chunk` con quel `process_id`, i nodi Neo4j restano tutti.
2. L'id workspace del processo e' `slugify(nome)` reso unico **contro il
   database workspace di adesso** (`unique_id`, [workspace_database.py:99](../backend/workspace_database.py#L99)).
   Dopo la cancellazione, lo slug `ciclo-passivo` e' di nuovo libero.
3. `scope._upsert` ([scope.py:46](../backend/memory/scope.py#L46)) mappa l'id
   workspace sul canonical con `ON CONFLICT (consultant_id, workspace_id) DO
   UPDATE SET name` — **la chiave e' per consulente, non per progetto ne' per
   cliente**, e sul conflitto restituisce la riga esistente.

### Cosa succede all'utente

- **Stesso cliente.** Il consulente cancella "Ciclo passivo" perche' le
  interviste caricate erano sbagliate. Lo ricrea. Il nuovo processo riceve lo
  slug `ciclo-passivo`, `scope.resolve` restituisce il **vecchio** processo
  canonical, e tutta l'evidenza cancellata e' di nuovo in scope: la chat del
  processo nuovo cita le interviste sbagliate. **Dati che l'utente ha cancellato
  tornano visibili.**
- **Cliente diverso.** Stesso nome di processo in un altro cliente dello stesso
  consulente — per un consulente di processo, "Ciclo passivo" in piu' clienti e'
  la norma. L'evidenza del cliente B viene scritta con il `process_id` del
  processo del cliente A. I **testi restano protetti** (le righe portano
  `client_id` di B, RLS e idratazione tengono), ma il nodo `Process` in Neo4j
  cambia proprietario a ogni scrittura (`SET n += props`, vince l'ultimo): per
  il cliente A l'espansione dal suo processo smette di funzionare.

### Evidenza

Nel database dev: il cliente `9e16…` ha 9 `kg_entity` e 3 `kg_source` con il
`process_id` di un processo del cliente `717d…`. In dev succede anche senza
cancellazioni, perche' ogni worktree ha il suo database workspace (lo crea
`scripts/new_agent_worktree.py`) e il canonical e' condiviso: gli slug si
ripetono fra sessioni. In produzione il percorso e' la cancellazione + riuso.

### Decisione — serve prima del codice

Due domande di prodotto, non tecniche:

1. **Cancellare un processo deve cancellare la sua evidenza nel cervello?**
   Oggi no, in silenzio. Le opzioni: (a) si', cascata sul canonical e su Neo4j
   (coerente con cio' che l'utente si aspetta, e con INV-10); (b) no, ma il
   processo canonical viene marcato come chiuso e mai piu' riassegnato.
2. **L'identita' canonical di un processo puo' dipendere da uno slug del nome?**
   Qualunque sia la risposta alla 1, la chiave `(consultant_id, workspace_id)`
   va almeno ristretta al progetto — o, meglio, l'id workspace deve essere
   stabile e non riusabile (uuid, o slug + suffisso casuale).

La parte tecnica, una volta decisa la 1: migration che cambia la chiave di
conflitto, cascata (o tombstone) in `delete_process` verso canonical e Neo4j,
e uno script che trova e separa i `process_id` gia' condivisi fra clienti. Mezza
giornata.

---

## ③ Piano dei branch

| branch | contenuto | prova | stima |
| --- | --- | --- | --- |
| `fix/graph-retrieval-budget` | GR-03, GR-02, GR-01, GR-12 — **fatto** | unit test deterministici | 1 g |
| `fix/process-delete-erases-evidence` | GR-13 — **fatto** | `tests/test_process_delete_erases_evidence.py` | 0,5 g |
| `fix/graph-lexical-italian` | GR-05 (strada A), GR-07 | test di stemming, `EXPLAIN` allegato al PR | 0,5 g |
| `fix/graph-vector-recall` | GR-06 | recall@k vs esatto = 1.0 | 0,5 g |
| `feat/retrieval-eval` | GR-08 (harness) | — (e' lo strumento) | 0,5 g + **tue 3 h** |
| `feat/graph-triple-ranking` | GR-04 | numeri prima/dopo da GR-08 | 0,5 g |
| `feat/speaker-aware-chunking` | GR-09 + re-embed | numeri da GR-08 | 1 g |
| — | GR-10, GR-11 | da pianificare | 2-3 g / decisione |

**Somma fix (GR-01..GR-07): ~2 giornate.** Piu' mezza giornata di harness e 3
ore tue di etichettatura per avere il numero che dice che sono chiusi.

La riga onesta: *due giornate per chiudere i sette problemi, una settimana per
poter dimostrare che sono chiusi.*

### Cosa serve da te, in ordine

0. **GR-13**: cancellare un processo cancella la sua evidenza? E l'identita'
   del processo canonical puo' dipendere dallo slug del nome? → sblocca il fix
   piu' urgente dell'elenco.
1. **GR-05, fork multilingua**: A (`'italian'` fisso) va bene? → sblocca il
   secondo branch.
2. **GR-02, whitelist relazioni**: quali tipi di relazione contano
   nell'espansione? Posso partire senza (il cap per-seed e' la parte che
   pesa), ma la whitelist e' una decisione di dominio, non tecnica.
3. **GR-08, 30-50 query etichettate**: il blocco vero. Senza, tre fix restano
   scommesse ragionate.
4. **GR-11**: decisione, prima di GR-10.

---

## ④ Cosa **non** va toccato

Scritto qui perche' un refactor del retrieval e' esattamente il momento in cui
si perdono invarianti pagate care:

- **`_hydrate` resta il confine.** GR-03 pre-filtra in Neo4j per non sprecare
  budget, **non** per sostituire il filtro in Postgres. Neo4j Community non ha
  subgraph ACL: se un giorno l'idratazione smette di ri-applicare lo scope, i
  fatti di un altro processo rientrano come nel test E2E V2.
- **Il fail-closed su scope vuoto.** `_text_search` con `source_ids == []`
  torna vuoto, non client-wide ([gateway.py:248](../backend/memory/gateway.py#L248)).
  Sembra un caso limite inutile fino al giorno in cui non lo e'.
- **`graph_retrieve` che non solleva.** L'`except Exception` finale con
  `degradation_counters.bump` e' voluto: il grounding che si spegne non deve
  abbattere la chat. I fix aggiungono segnale **dentro** la risposta, non
  eccezioni.
- **L'LLM propone, il runtime dispone.** Vale per il resolver (P2) e per il
  reranker (P3.2, con l'ordine LLM validato prima dell'uso). Il ranking delle
  triple di GR-04 e' **deterministico**: non diventa un secondo giudice LLM sul
  path di grounding.
- **`EMBED_VERSION` e il CHECK sulla dimensione.** GR-09 li usa. Non aggirarli
  con un embedding di dimensione diversa "solo per provare".

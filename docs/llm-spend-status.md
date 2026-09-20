# Spesa LLM — stato dei lavori

Documento vivo. Il piano sta in [`llm-gateway-plan.md`](llm-gateway-plan.md) e
non si tocca: e' la direzione. Qui c'e' cosa e' stato fatto, cosa manca, e
qual e' il prossimo passo.

**A chi serve:** a piu' sessioni agente in parallelo, e a Sohayb per sapere dove
siamo senza rileggere i diff.

**Come si usa.** Chi prende in mano il lavoro legge §② e fa quello. Chi lo posa
aggiorna §① (cosa ha chiuso), §② (il prossimo passo, uno solo) e §⑥ (la riga di
log). Un passo non si dichiara fatto se i suoi test non sono verdi: §① distingue
*scritto* da *verificato*, ed e' la distinzione che vale.

Ultimo aggiornamento: 2026-09-20.
Branch di lavoro: `chore/llm-spend-p0` (worktree `.claude/worktrees/llm-spend-p0`).

---

## ① Stato

### P0 — Fermare gli sprechi

| # | Cosa | Stato |
| --- | --- | --- |
| P0.1 | Test senza chiave del provider (invariante L6) | **fatto, verificato** |
| P0.2 | Un solo livello di retry invisibile: SDK a 0 | **fatto**, suite in verifica |
| P0.3 | Timeout proporzionato alla lunghezza dell'input | **fatto**, suite in verifica |
| P0.4 | Progetti e chiavi separati dev / eval / prod, con tetto | **non iniziato** — serve Sohayb (§④) |
| P0.5 | Tracing LangSmith spento | **non fatto** — una riga in `.env`, §④ |
| P0.6 | Riferimenti rotti nel piano parziale intercettati prima del merge | **rinviato a P2** (§⑤) |

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

Convertiti a opt-in i 7 moduli che pagavano: `test_gateway_memory`,
`test_client_scoped_recall`, `test_kg_vector_retrieval`, `test_entity_resolution`
(`TestVectorPath` + il test worker/Neo4j), `test_kg_ingest_queue` (E2E dal tool),
`evals/test_golden_set`, `evals/test_canvas_modeling_eval`,
`evals/test_conformance_eval`.

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

**P0.3 — timeout proporzionato.** `llm_config.timeout_for_input(characters)`:
pavimento `model_timeout_seconds` (45 s) + 15 s per 1.000 caratteri, tetto 300 s.
Un'intervista da 4.000 caratteri passa da 45 s a 105 s. La cache
dell'estrattore e' chiavata su scaglioni di 2.000 caratteri
(`process_understanding._timeout_bucket`), altrimenti la prima nota corta
avrebbe fissato il timeout del caso breve per ogni intervista successiva.

### P1–P5

Non iniziati. Vedi il piano.

---

## ② PROSSIMO STEP

**Chiudere la verifica di P0.2 / P0.3, poi il registro dei consumi minimo.**

1. Far girare la suite intera e sistemare cio' che il cambio di timeout e retry
   ha mosso (`uv run pytest -q`, serve Postgres su — §⑤). Al momento della
   scrittura e' in corso: **P0.2 e P0.3 sono scritti, non ancora verificati.**
2. Poi P1, e il taglio consigliato e' piu' corto di quanto dice il piano: i
   punti di chiamata passano gia' quasi tutti da `backend/llm_config.py`, quindi
   il gateway non e' un pezzo nuovo — e' `chat_openai_kwargs` che smette di
   restituire kwargs e inizia a eseguire. **1-2 giorni, non una settimana.**
   Il minimo che serve per rispondere a «dove sono andati i soldi ieri»:
   - un `contextvar` con l'operazione corrente (tipo, tenant, progetto, processo);
   - una tabella dei consumi su Postgres;
   - `response.usage_metadata`, che langchain **restituisce gia'**: non serve
     telemetria nuova, serve scriverla da qualche parte.

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
4. **Gli embedding nel gateway.** Il piano li elenca fra i punti di chiamata ma
   poi il registro dei compiti parla solo di chat. Nell'ingestione KG il volume
   sta negli embedding. Il gateway li copre, o il registro mente.
5. **L'evento di validazione.** Il KPI di punta del piano e' «costo per AS-IS
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
| 2026-09-20 | P0.1 test a opt-in, P0.2 retry SDK a 0, P0.3 timeout proporzionato | branch `chore/llm-spend-p0` |

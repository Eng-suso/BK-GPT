# Fornitori e invii dati

> **Documento vivo.** È la risposta a «quali fornitori ricevono i dati del cliente,
> quali dati e dove», per DPA, registro dei subresponsabili e questionari di
> sicurezza (SEC-06, SEC-13, gate G3 e G7 del riferimento di sicurezza).
>
> **Fonte di verità per le destinazioni:** [`backend/llm/egress.py`](../../backend/llm/egress.py).
> Il test `tests/llm/test_egress.py` fallisce se una destinazione o un compito LLM
> del codice non compare qui. Lo stato reale di un'installazione si legge da
> `GET /v1/observability/egress` e in **Impostazioni → Dati inviati all'esterno**.

Ultimo aggiornamento: 23 novembre 2026.

## Come si legge lo stato

| Stato | Significato |
|---|---|
| **NOT VALIDATED** | Nessuna prova raccolta. Non dichiarare nulla al cliente su questo punto. |
| **IN PROGRESS** | Verifica avviata: c'è un documento del fornitore, ma non è ancora stato confrontato con il nostro uso. |
| **PASS** | Prova archiviata (link al DPA firmato, impostazione verificata nella console del fornitore, data della prova). |
| **FAIL** | Verificato e non adeguato: la destinazione va spenta o sostituita prima di usare dati reali. |

Al 23/11/2026 nessuna voce contrattuale è verificata: tutte sono **NOT VALIDATED**.

## 1. Destinazioni nel codice

Una riga per ogni punto da cui i dati possono uscire. «Attiva quando» dice quale
configurazione la accende; una destinazione spenta resta elencata.

| Chiave | Fornitore (default) | Host di default | Cosa riceve | Attiva quando | Compiti |
|---|---|---|---|---|---|
| `llm_chat` | OpenAI, o il fornitore di `OPENAI_BASE_URL` | `api.openai.com` | Interviste, testi dei documenti, messaggi di chat, piani di processo, scenari | `OPENAI_API_KEY` impostata | Tutti tranne embedding e trascrizione (vedi §2) |
| `llm_embedding` | OpenAI | `api.openai.com` | Frammenti di documenti e interviste | `OPENAI_API_KEY` impostata | `embedding` |
| `transcription` | OpenAI | `api.openai.com` | **File audio** delle interviste (voce = dato personale) | `OPENAI_API_KEY` impostata | `transcription` |
| `transcription_live` | OpenAI Realtime | `api.openai.com` (wss) | **Audio dal microfono** in tempo reale | `OPENAI_API_KEY` impostata | — (WebSocket diretto, non passa dal gateway) |
| `memory_extraction` | OpenAI, o il fornitore di `MEM0_LLM_BASE_URL` | `api.openai.com` | Fatti estratti dalle conversazioni (Mem0) | `OPENAI_API_KEY` + `MEM0_DATABASE_URL` | — (libreria Mem0) |
| `memory_embedding` | OpenAI | `api.openai.com` | Testi delle memorie (Mem0) | come sopra | — (libreria Mem0) |
| `tracing` | LangSmith (LangChain Inc.) | `api.smith.langchain.com` | **Prompt e risposte interi** di ogni chiamata al modello | `LANGSMITH_TRACING=true` | Tutti quelli che passano da LangChain |
| `web_search` | Tavily | `api.tavily.com` | Query di ricerca generate dall'agente (possono citare il cliente) | `TAVILY_API_KEY` impostata | — (strumento dell'agente) |
| `document_reader` | docling-serve, **self-hosted** | `docling` / `127.0.0.1` | PDF, DOCX e PPTX caricati, interi | sempre | — |
| `simulation_engine` | Prosimos, **self-hosted** | `prosimos` / `127.0.0.1` | Modelli BPMN e scenari (nomi di attività e ruoli) | sempre | — |
| `identity_provider` | Supabase Auth (cloud), o la CLI locale in dev/prod-sim | `<ref>.supabase.co` | Email e identificativo dei consulenti; il backend legge solo le chiavi pubbliche (JWKS), il browser fa il login | `DELIR_AUTH_ENABLED=true` + `DELIR_AUTH_PROVIDER=supabase` | — |

### Cose che dalla lettura del codice non erano ovvie

1. **Embedding e trascrizione vanno sempre a OpenAI**, anche quando la chat è
   spostata su un altro fornitore con `OPENAI_BASE_URL`. Per gli embedding è un
   vincolo dello schema (vettori a 1536 dimensioni, INV-4). Cambiare fornitore
   della chat **non** toglie OpenAI dai subresponsabili.
2. **La trascrizione live non passa dal gateway**: apre un WebSocket diretto
   verso OpenAI Realtime. Ora l'URL viene dal registro e il permesso è
   controllato, ma l'audio esce comunque grezzo, prima di qualunque filtro PII.
3. **LangSmith riceve tutto quello che riceve il modello.** Accenderlo in
   produzione aggiunge un subresponsabile con gli stessi dati del modello.
4. **Il tracer locale** (`data/traces/*.jsonl`) scriveva i testi dei prompt anche
   in produzione. Dal 23/11/2026 i testi si scrivono solo con `DELIR_ENVIRONMENT`
   `dev`, `local` o `test`. In staging e prod restano solo tempi, token ed esiti, e
   `DELIR_LOCAL_TRACE_PAYLOAD=1` non li riaccende.

## 2. Compiti LLM e dati inviati

Ogni chiamata al modello dichiara un compito (`backend/llm/tasks.py`). Qui c'è
cosa porta con sé. La destinazione è quella risolta da `egress.py`.

| Compito | Destinazione | Dati del cliente nel prompt | Note |
|---|---|---|---|
| `plan_extraction` | `llm_chat` | Testo integrale di interviste e documenti | Estrazione del processo dalle fonti |
| `source_claims` | `llm_chat` | Porzioni di un file caricato | Affermazioni legate alla fonte |
| `source_reconcile` | `llm_chat` | Affermazioni di due fonti | Confronto fra fonti |
| `plan_quality` | `llm_chat` | Piano di processo estratto | |
| `plan_unification` | `llm_chat` | Piani di più fonti | |
| `conformance_audit` | `llm_chat` | Piano + estratti delle fonti | |
| `entity_resolution` | `llm_chat` | Nomi di entità (persone, ruoli, sistemi) | Solo i casi che il codice non chiude |
| `retrieval_rerank` | `llm_chat` | Frammenti recuperati + domanda | |
| `playbook_extraction` | `llm_chat` | Conversazioni del consulente | Memoria procedurale |
| `playbook_generalization` | `llm_chat` | Playbook già estratti | |
| `chat_turn` | `llm_chat` | Messaggi di chat + contesto recuperato | |
| `context_routing` | `llm_chat` | Messaggio del consulente | |
| `eval_judge` | `llm_chat` | Output dell'agente sui casi di test | Solo eval, mai in produzione |
| `claim_matching` | `llm_chat` | Affermazioni + nomi delle attività | |
| `simulation_what_if` | `llm_chat` | Frase del consulente + id dello scenario | |
| `simulation_narrative` | `llm_chat` | KPI già calcolati (segnaposti) | Non scrive cifre proprie |
| `embedding` | `llm_embedding` | Frammenti di testo | |
| `transcription` | `transcription` | Audio | |

## 3. Registro dei fornitori

Comprende anche i fornitori di infrastruttura, che il registro del codice non
vede. Le colonne contrattuali vanno compilate con una prova (link o data), non
a memoria.

| Fornitore | Ruolo | Dati | Destinazioni / uso | Regione | DPA | Conservazione e training | Trasferimento extra-SEE | Stato |
|---|---|---|---|---|---|---|---|---|
| OpenAI | Subresponsabile | Contenuti del cliente, audio | `llm_chat`, `llm_embedding`, `transcription`, `transcription_live`, `memory_*` | Da verificare (US di default; data residency UE da valutare) | Da firmare | API: niente training di default; conservazione per abuse monitoring da verificare, Zero Data Retention da richiedere | Sì, se US: SCC + valutazione | NOT VALIDATED |
| LangChain Inc. (LangSmith) | Subresponsabile, se acceso | Prompt e risposte interi | `tracing` | Da verificare (esiste un endpoint UE) | Da firmare | Conservazione delle tracce da configurare | Da verificare | NOT VALIDATED (spento in prod di default) |
| Tavily | Subresponsabile, se acceso | Query di ricerca | `web_search` | Da verificare | Da verificare | Da verificare | Da verificare | NOT VALIDATED (spento senza chiave) |
| Oracle (OCI) | Hosting | Tutto, a riposo | VM, Postgres, Neo4j, volumi | Da verificare (regione della VM) | Da verificare | — | Da verificare | NOT VALIDATED |
| Cloudflare | Rete (Tunnel, Access) | Traffico in transito (TLS terminato al bordo) | Ingresso API | Globale | Da verificare | — | Sì | NOT VALIDATED (previsto, A1) |
| Vercel | Hosting del frontend | Frontend statico; nessun dato cliente previsto | — | Da verificare | Da verificare | — | Da verificare | NOT VALIDATED (previsto) |
| Supabase | Identità (Track B) | Email e identità degli utenti | `identity_provider` | UE (Frankfurt) prevista | Da verificare | — | Da verificare | NOT VALIDATED (verifier B1 pronto, progetti cloud da creare) |
| GitHub (GHCR, Actions) | Codice e immagini | Codice; **nessun dato cliente** ammesso | CI, registry | US | Da verificare | — | Sì | NOT VALIDATED |
| docling-serve | Self-hosted | Documenti | `document_reader` | Sulla VM | — | — | No | Interno |
| Prosimos | Self-hosted | Modelli di processo | `simulation_engine` | Sulla VM | — | — | No | Interno |

## 4. La regola nel codice

- **Host interno** (loopback, rete privata, nome di servizio docker senza punti):
  self-hosted, sempre permesso.
- **Host esterno in staging o prod:** deve stare in `DELIR_EGRESS_ALLOWED_HOSTS`.
  Se una destinazione attiva è fuori lista **l'app non parte**, e l'errore le
  elenca tutte. Se la chiamata ci arrivasse comunque, viene rifiutata con
  `EgressBlocked` e il rifiuto finisce nel registro dei consumi (fail closed).
- **In sviluppo** una lista vuota permette tutto, ma una lista non vuota vale già:
  la configurazione di produzione si prova in locale.
- `ops/docker-compose.prod.yml` e `ops/docker-compose.staging.yml` dichiarano
  `api.openai.com` come unico host. Accendere LangSmith o Tavily vuol dire
  anche aggiungere il loro host, dopo averli registrati qui.
- Mem0 e la ricerca web, se bloccati, **si spengono** invece di uscire.

## 5. Aggiungere un LLM o un fornitore alla pipeline

Vale per ogni nuovo modello su un endpoint diverso (Gemini, Mistral, Anthropic,
un modello self-hosted), per ogni compito spostato su un altro fornitore e per
ogni nuovo servizio esterno.

1. **Registro del codice.** Il compito si instrada in `_llm_url_for()` in
   `backend/llm/egress.py`. Un servizio nuovo diventa una `Destination` con
   `purpose`, `url`, `data` e la condizione `active`. Il client si costruisce
   solo in un modulo che chiama `egress.require(...)`: il test
   `test_nessun_client_sdk_fuori_dai_punti_registrati` blocca gli altri.
2. **Questo documento.** Una riga in §1 o §2 (il test lo esige) e una in §3 con
   regione, DPA, conservazione, training e trasferimenti. Finché lo stato è
   NOT VALIDATED, il fornitore riceve solo dati di test o dati che il cliente ha
   autorizzato per iscritto per quel fornitore.
3. **Minimizzazione.** Scrivere nella riga del compito cosa entra nel prompt.
   Se è testo integrale delle fonti e il fornitore non ha un DPA firmato, il
   compito non va spostato.
4. **Allowlist.** Aggiungere l'host a `DELIR_EGRESS_ALLOWED_HOSTS` dell'ambiente,
   dopo i punti 2 e 3, non prima.
5. **Comunicazione al titolare.** Un nuovo subresponsabile va comunicato al
   cliente secondo il DPA (art. 28.2 GDPR) prima di usarlo con i suoi dati.
6. **Verifica.** `GET /v1/observability/egress` sull'ambiente deve mostrare la
   destinazione attiva, autorizzata, con l'host atteso.

## 6. Cosa manca (prossimi passi)

- **Instradamento per compito:** oggi tutti i compiti di chat usano lo stesso
  endpoint e la stessa chiave. Con più LLM nella pipeline serve una tabella
  compito → (fornitore, modello, chiave), da aggiungere in `_llm_url_for()` e nei
  costruttori dei client, così il registro resta l'unica fonte.
- **Policy per classe di dato:** l'allowlist decide *dove* si può andare, non
  *cosa* può andarci. Il passo successivo è legare ogni destinazione alle
  categorie di dato ammesse (per esempio: audio solo verso fornitori con DPA
  firmato) e collegarlo al Privacy Gateway (P1).
- **Compilare §3** con le prove: DPA firmati, regioni, impostazioni di
  conservazione e Zero Data Retention.

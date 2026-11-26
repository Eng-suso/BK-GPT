# Contatore d'uso e limiti per la prova dei consulenti

Stato: **proposta**, nessun codice cambiato. Data: 2026-11-26.

Obiettivo: far provare DeliR ai consulenti per X giorni senza andare in perdita. Il
consulente deve sapere in ogni momento **quanto ha usato, quanto gli resta e quando si
azzera**, come in Claude o in Codex.

---

## 1. Come lo fanno gli altri (ricerca)

| | Claude | Codex |
|---|---|---|
| Finestra breve | 5 ore, **parte dal primo messaggio** (non a orario fisso) | 5 ore |
| Finestra lunga | settimanale, 7 giorni, su tutti i modelli | settimanale |
| Pool | unico per tutte le superfici (web, desktop, Code) | unico |
| Cosa vede l'utente | percentuale usata + ora del reset | percentuale + reset, crediti |
| Oltre il limite | stop fino al reset (o crediti extra) | stop o crediti ChatGPT |

Lezioni utili:

- I due limiti sono **indipendenti**: si può finire la settimana senza mai toccare le 5
  ore. Va mostrato chiaramente quale dei due sta per finire.
- All'utente si mostra una **percentuale**, non i token: i token non dicono niente a un
  consulente, e un'operazione pesante e una leggera costano cose molto diverse.
- La lamentela più frequente (forum Codex) è la **poca trasparenza**: «un prompt mi ha
  mangiato il 7% della settimana e non so perché». Serve dire *cosa* ha consumato.
- Iniziare una nuova conversazione non azzera niente: il conto è per persona.

Pattern tecnici: finestra scorrevole su un registro con timestamp (quello che abbiamo già),
controllo **prima** della chiamata con stima, e conciliazione **dopo** con i token veri.

## 2. Cosa c'è già nella code base (ed è tanto)

DeliR ha già quasi tutto il lato "misura":

- **Un solo punto di passaggio** per le chiamate: `backend/llm/gateway.py` (`run`, `embed`,
  `transcribe`, `record_streamed_usage` per la chat) e `backend/llm/chat_client.py`. Una
  regola CI vieta `ChatOpenAI` fuori da `backend/llm/`.
- **Ogni chiamata è dentro un'operazione** (`backend/llm/operation.py`): tipo, tenant,
  progetto, processo, operazione padre.
- **Un registro dei consumi** per chiamata: tabella `workspace_llm_usage`
  (`backend/workspace_storage.py:765`), con token input/output/reasoning/cached, esito,
  durata, tentativo, costo stimato.
- **Query di lettura** pronte in `backend/llm/ledger.py` (totali per finestra, per compito,
  per giorno, costo dei retry, peso del ragionamento).
- **Listino** da configurazione (`LLM_PRICES_JSON`, `backend/llm/prices.py`).

Quindi il contatore **non** è un sistema nuovo: è (a) chiudere i buchi della misura,
(b) aggiungere il controllo prima della chiamata, (c) mostrarlo.

## 3. I buchi che vanno chiusi prima

1. **Non c'è l'utente.** `Operation` e `workspace_llm_usage` hanno il tenant ma non il
   consulente. Il JWT Supabase ha `sub` (`backend/auth/supabase_jwt.py`), ma non arriva
   al registro. Senza, il limite è per tenant, non per persona.
2. **Mem0 è fuori dal registro.** `backend/memory/mem0_client.py` costruisce un
   `mem0.Memory` con il suo client OpenAI. Ogni `memory.add()` (worker
   `backend/workers/mem0_worker.py`, `memory/semantic/semantic_store.py`) fa estrazione dei
   fatti con LLM + decisione di aggiornamento con LLM + embedding; ogni `memory.search()`
   fa un embedding. **Nessuna di queste chiamate viene contata.** È il primo sospettato
   per «il knowledge graph mi mangia i token senza che si veda».
3. **Il costo può essere NULL.** Se `LLM_PRICES_JSON` è vuoto i token si contano ma il
   costo no. Per un limite in denaro il listino va configurato per tutti i modelli usati
   (`ledger.modelli_da_prezzare` dice quali mancano).
4. **Nessun controllo prima della chiamata.** Oggi si registra dopo: si può solo
   osservare, non fermare.
5. **I worker non hanno l'utente.** L'ingestione del KG (`workers/ingest_worker.py`) apre
   l'operazione con progetto e processo, ma non sa chi ha caricato il documento.

## 4. Dove si bruciano i token (ipotesi, da confermare con il registro)

In ordine di sospetto:

1. **Turno di chat.** Il prompt di scope arriva fino a `agent_scope_context_budget_tokens
   = 48_000` token, e il ciclo agente può fare fino a `agent_max_decision_steps = 8` passi:
   nel caso peggiore **~400k token di input per un solo turno**, più la chiamata di
   instradamento. Il caching automatico del fornitore aiuta solo se il prefisso resta
   identico fra un passo e l'altro.
2. **Ingestione del KG** (`memory/knowledge_graph/canonical.py`,
   `entity_resolution.py`): embedding di ogni chunk, embedding di ogni nome di entità, e
   **una chiamata LLM per ogni entità** che il confronto deterministico non chiude.
   Un documento con 200 entità ambigue = 200 chiamate.
3. **Mem0** (vedi buco 2): più chiamate LLM per ogni fatto, invisibili.
4. **Estrazione piano / audit di conformità** con `reasoning_effort="medium"` su tutta la
   fonte: poche chiamate, ma grosse.

Prima misura da fare: una giornata d'uso tipica di un consulente, poi
`ledger.per(... "task")` e `ledger.per(... "operation_kind")`. Ci dice quanto costa un
consulente al giorno, che è il numero da cui si ricava il budget.

## 5. Design proposto

### Unità: crediti, mostrati come percentuale

- Internamente il consumo si misura in **costo stimato** (dal listino), non in token: un
  token di embedding e uno di ragionamento non costano uguale, e il tuo rischio è il
  denaro.
- Al consulente si mostra **una percentuale** e l'ora del reset. Niente token nel percorso
  normale; il dettaglio per attività ("Chat", "Lettura documenti", "Mappa delle
  conoscenze", "Simulazione") sta in una pagina "Utilizzo".

### Tre limiti

| Limite | Finestra | Perché |
|---|---|---|
| **Sessione** | 5 ore dal primo uso, scorrevole | distribuisce l'uso, protegge da un pomeriggio che brucia tutto |
| **Settimana** | 7 giorni dall'inizio della prova | il vero tetto di spesa |
| **Prova** | X giorni, totale | data di fine + tetto assoluto: è la garanzia di non andare in perdita |

I valori stanno in una tabella `usage_plan` (per consulente o per tenant), non nel codice:
così si cambiano per un singolo consulente senza rilascio.

### Dove si mette il controllo (backend)

Un modulo nuovo `backend/llm/budget.py`, chiamato **dentro il gateway**, così vale per tutto
il prodotto senza toccare gli agenti:

```
gateway.run / embed / transcribe / chat_client  ──►  budget.check(operation, task)
                                                        │  sotto il limite → passa
                                                        │  sopra → BudgetExhausted
                         chiamata al modello
                                                        ▼
                    usage.record(...)  ──►  la riga ha già user_id e costo
```

- `Operation` prende `user_id` (dal JWT); `workspace_llm_usage` prende la colonna
  `user_id` con indice (migrazione `migrations_workspace`).
- `budget.check` legge la somma del registro nelle due finestre (indice su
  `user_id, created_at`), con una cache breve in memoria.
- I compiti grossi (estrazione, audit) fanno una **stima prima** dall'`input_characters`
  già passato al gateway; dopo, il registro concilia con i token veri.
- **Regole di comportamento al limite** (da decidere, proposta):
  - un turno di chat iniziato **finisce** sempre; si blocca il turno successivo;
  - i lavori in background `deferrable` (già marcati in `tasks.py`) **restano in coda** e
    ripartono al reset, non si perdono;
  - l'ingestione del KG si attribuisce a chi ha caricato il documento (`user_id` nel
    payload del job).
- Mem0 entra nel registro: o con un `http_client` OpenAI che legge `usage` dalle risposte
  (da verificare che la config di Mem0 lo accetti), o avvolgendo `add`/`search` con una
  riga per chiamata. Finché non è contato, il limite è aggirabile proprio dove costa.

### API e interfaccia

- `GET /api/usage/me` → `{session: {used_pct, resets_at}, week: {used_pct, resets_at},
  trial: {ends_at, days_left}, by_activity: [...]}`.
- **TopBar** (`frontend/src/components/shell/TopBar.tsx`): un indicatore compatto, anello o
  barra, che diventa ambra all'80% e rosso al 95%. Al clic: le due barre e l'ora di reset.
- Pagina **Utilizzo** con il dettaglio per attività, in linguaggio di business.
- Messaggio al limite: «Hai usato tutta la sessione. Riprende alle 15:20. Il lavoro in
  corso è salvato.» Nessun errore tecnico.
- Avviso all'80% dentro la chat, prima di lanciare un'operazione grossa: «Rigenerare il
  BPMN usa circa il 6% della settimana».

## 6. Il budget

Formula: `budget settimanale per consulente = budget totale della prova / n. consulenti /
n. settimane`, con un margine (es. 20%) per i lavori in background. Il limite di sessione
si mette intorno a **1/4–1/3 del settimanale**, così servono almeno 3–4 sessioni per
finire la settimana.

I numeri veri vanno presi dalla misura del punto 4: senza sapere quanto costa una giornata
tipica, qualsiasi limite è un tiro a caso (troppo basso → il consulente si blocca e la
prova va male; troppo alto → perdi soldi).

## 7. Piano a punti (piccole PR)

1. **Misura completa** – `user_id` in `Operation` e nel registro; Mem0 nel registro;
   listino configurato; `user_id` nei job dei worker. *Meta: 100% delle chiamate con
   utente e costo, verificato su una sessione reale.*
2. **Ridurre lo spreco** (prima dei limiti, altrimenti i limiti scattano subito) – cache
   dei verdetti di entity resolution e degli embedding per hash del testo; giudizio di
   entity resolution a gruppi invece che una chiamata per entità; prefisso del prompt di
   scope stabile fra i passi (caching); budget di scope dei passi successivi più piccolo;
   estrazione Mem0 accorpata/differita. *Meta: costo di una giornata tipica −X% a parità di
   risultato.*
3. **Controllo** – `budget.py`, `usage_plan`, `BudgetExhausted` gestito in chat e nei
   worker. Test sulle finestre (5h dal primo uso, 7 giorni, fine prova).
4. **Interfaccia** – endpoint, indicatore in TopBar, pagina Utilizzo, messaggi;
   screenshot Playwright desktop e mobile.
5. **Amministrazione** – cambiare il piano di un consulente, azzerare, estendere la prova.

## 8. Decisioni che servono da te

1. Quanti consulenti, quanti giorni di prova, e quale budget totale in euro.
2. Un consulente = un tenant nella prova, o più consulenti nello stesso tenant?
3. Al limite: blocco duro, o "modalità ridotta" (chat sì con modello economico, lavori
   pesanti no)?
4. Ricarica: prevedi di dare crediti extra a mano a chi li chiede?

## Fonti

- [Claude – usage and length limits](https://support.claude.com/en/articles/11647753-usage-and-length-limits)
- [Claude Usage Limits: 5-Hour Sessions, Weekly Caps](https://dupple.com/learn/claude-usage-limits)
- [TechCrunch – Anthropic unveils new rate limits](https://techcrunch.com/2025/07/28/anthropic-unveils-new-rate-limits-to-curb-claude-code-power-users/)
- [Codex Pricing](https://developers.openai.com/codex/pricing)
- [TechRepublic – 5-hour Codex limit back for Plus](https://www.techrepublic.com/article/news-openai-five-hour-codex-limit-chatgpt-plus/)
- [Forum OpenAI – weekly limit ran out without hitting 5-hour](https://community.openai.com/t/weekly-limit-ran-out-even-though-i-never-hit-the-5-hour-limit/1376981)
- [TrueFoundry – LLM token rate limiting and budgets](https://www.truefoundry.com/es/blog/llm-token-rate-limiting-budgets)
- [llm-budget-window (finestre scorrevoli su token e costo)](https://docs.rs/crate/llm-budget-window/latest/source/README.md)
- [agentgateway – budget limits](https://agentgateway.dev/docs/kubernetes/latest/llm/cost-controls/budget-limits/)

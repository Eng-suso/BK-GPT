# Dove si bruciano i token, cosa è stato corretto, a che punto siamo

Data: 2026-11-26. Branch `claude/nice-newton-3kmoj9`. Segue `PROPOSTA.md`.

Metodo: lettura del codice, esperimenti riproducibili, misure nei test.
Questo ambiente non ha una chiave del fornitore: **le misure contano chiamate,
testi e token nei test, non euro reali**. Il prossimo passo è leggere il
registro su una giornata vera (vedi §5).

## 1. Problemi trovati e corretti

| # | Problema | Effetto | Correzione | Prova |
|---|---|---|---|---|
| 1 | **Doppio conteggio nella chat.** Le chiamate `llm.run()` fatte dai tool dentro il grafo (estrazione, rerank, giudizi) passavano nello stream di LangGraph e il runtime le risommava nella riga `chat_turn`. | Il registro gonfiava il costo della chat, e un contatore d'uso avrebbe tolto credito due volte. | I client del gateway portano il tag `delir:ledger-recorded`; il runtime non li riconta. | `tests/llm/test_turn_accounting.py`: 1000 token di tool spariscono dalla riga del turno, i nodi della chat restano. |
| 2 | **Mem0 invisibile.** `mem0.Memory` ha i suoi client OpenAI: estrazione dei fatti ed embedding della memoria non lasciavano nessuna riga. | Spesa vera, in background, non misurata. | `backend/llm/mem0_meter.py` avvolge i `create()` dei client di Mem0; il worker apre `MEMORY_PROJECTION`. Nuovi compiti `memory_extraction`, `memory_embedding`. | `tests/llm/test_mem0_meter.py`, anche contro la libreria installata. |
| 3 | **Nessun consulente nel registro.** C'era il tenant, non la persona. In più `require_principal` era una dipendenza sincrona: quello che impostava nel contesto restava nel thread del pool e non arrivava alla rotta. | Impossibile un limite per consulente. | `Operation.user_id` (dalla richiesta, dal padre o dal job), colonna `workspace_llm_usage.user_id` + indice `(user_id, created_at)`, `require_principal` `async`. | `tests/llm/test_usage_user.py`, con un test HTTP che fallisce con la vecchia dipendenza. |
| 4 | **Lavoro in background senza padrone.** Lettura delle fonti, confronto, ingestione nel grafo giravano nei worker senza sapere chi li aveva chiesti. | Spesa attribuita a nessuno. | `workspace_sources.uploaded_by`; i job del grafo portano `user_id`. | Suite completa verde. |
| 5 | **Il knowledge graph ri-embeddava la stessa intervista.** `write_evidence` calcolava i vettori di tutti i chunk *prima* di controllare se la sorgente c'era già. Ogni pacchetto di evidenze porta con sé l'intervista intera. | Un'intervista si pagava una volta per pacchetto. | Il controllo sull'hash viene prima dell'embedding; il risparmio si registra come `cache_hit`. | `tests/knowledge_graph/test_source_reembedding.py`: 3 pacchetti, **18 testi embeddati prima, 8 dopo**. Con 30 chunk e 10 pacchetti: 300 → 30. |
| 6 | **Il riassunto del thread finiva dentro la chat.** | Il costo della manutenzione del contesto non si poteva leggere. | Compito `thread_summary`. | `tests/llm/test_llm_operation_wiring.py`. |
| 7 | **Nessuna lettura per persona e per cache.** | Il contatore non aveva la sua query. | `ledger.totale(user_id=...)`, dimensione `user_id`, `Totale.quota_in_cache`; `scripts/llm_spend.py` li stampa. | `tests/llm/test_llm_ledger_read.py`. |

## 2. Dove vanno i token, misurato

Il costo fisso di **ogni** chiamata dell'agente, prima del contesto e della
conversazione:

| Pezzo | Token (stima, caratteri/4) |
|---|---|
| Memoria procedurale (`how_to_act.md`) | ~1.600 |
| Tool dello specialista *modeling* | **~14.000** (`prepare_process_understanding_review` ~7.100, `amend_process_plan` ~6.000) |
| Tool dello specialista *evidence* | **~12.000** (`manage_process_evidence` ~3.300, i due tool del grafo ~2.400 ciascuno) |
| Tool *discovery* | ~1.600 |
| Contesto di scope (piano, modello, XML) | fino a 48.000 (`agent_scope_context_budget_tokens`) |

Un passo dello specialista di modellazione con un piano grande può partire da
~60.000 token di input, e un turno ha fino a 8 passi. Il fornitore fattura a
prezzo di cache (circa il 10%) solo il prefisso identico al passo prima.
Strumenti e memoria procedurale sono statici e quindi in cache. Il contesto di
scope cambia appena un tool modifica il piano.

Cosa **non** è il problema, misurato sul codice:

- **Entity resolution:** circa una chiamata da ~400 token per ogni nome *nuovo*
  che il confronto deterministico non chiude. Dopo il giudizio il nome diventa
  alias o entità, quindi non si ripaga. Va tenuta d'occhio, ma non è il
  grande consumatore.
- **La conversione degli schemi dei tool:** inline o con `$defs` la dimensione è
  la stessa (6.962 contro 7.235 token). Gli schemi sono grandi di natura: 32
  modelli annidati.

## 3. DeliR rispetto a Claude e ChatGPT

Valutazione onesta, voce per voce.

| Capacità | Claude / ChatGPT | DeliR oggi |
|---|---|---|
| Ogni chiamata misurata, attribuita, con esito e retry | Sì | **Sì**, dopo questa PR anche Mem0, il riassunto e per persona. Il registro è più ricco del necessario (versione del prompt, impronta del contesto). |
| Limite per persona (5 ore + settimana), visibile all'utente | Sì, con percentuale e ora del reset | **No.** Ci sono il dato e la query; mancano `budget.py`, il piano d'uso, l'interfaccia. È il prossimo punto. |
| Blocco prima della chiamata | Sì | **No.** Oggi si registra dopo. |
| Cache del prompt progettata | Prefisso stabile, strumenti caricati su richiesta | **Parziale.** L'ordine dei messaggi è giusto (statico prima, variabile dopo); gli strumenti si mandano tutti a ogni passo e non c'è `prompt_cache_key`. |
| Modello per compito | Modelli piccoli per lavori piccoli | **No.** Tutti i compiti di chat usano `openai_model`; il registro dei compiti è pronto per sceglierlo per compito, ma la scelta va fatta con gli eval. |
| Lavoro rinviabile a prezzo ridotto (Batch/Flex) | Sì | **No.** I compiti `deferrable` sono marcati ma non usati. |
| Compattazione del contesto | Sì | **Sì**: riassunto del thread, budget di scope con troncamento dichiarato. |
| Guardrail del ciclo agente | Sì | **Sì**: passi, chiamate ai tool e scadenza per turno. |

In sintesi: la **base di misura** di DeliR è all'altezza, e in alcuni punti è più
rigorosa di quanto serva a un prodotto di questa età. Non è ancora all'altezza
sul **controllo** (limiti e blocco) e sull'**ingegneria del costo** (strumenti su
richiesta, modello per compito, batch). Sono queste due cose, non la misura, a
separare oggi DeliR da Claude e ChatGPT.

## 4. Limiti noti di questa PR

- **Identità con il token condiviso.** Con `DELIR_API_TOKEN` (senza Supabase) o con
  l'autenticazione spenta, il consulente viene dall'header `X-DeliR-User-ID`, che
  il client può scegliere. Per misurare va bene; per **far rispettare** un limite
  per persona no. I limiti per persona vanno accesi solo con Supabase, dove
  l'identità è il `sub` del token.
- **Lavoro in background ancora senza consulente:** la proiezione in Mem0
  (`mem0_worker`), la sintesi del piano (`plan_worker`) e l'audit di conformità
  (`conformance_worker`). Le loro righe finiscono in «(nessuno)». Il prossimo
  passo è portare l'utente nelle loro code, come fanno ora le fonti e
  l'ingestione nel grafo.
- **Mem0 e i thread.** Con mem0 2.0.17 embedding e chiamate al modello girano nel
  thread di chi chiama (il pool interno fa solo ricerche vettoriali). Se una
  versione futura le spostasse in un pool, le righe finirebbero sotto
  un'operazione orfana: il contatore `llm_usage:mem0_call_without_operation` è
  il segnale da guardare dopo un aggiornamento di Mem0.

## 5. Cosa fare adesso, in ordine

1. **Misura vera:** listino in `LLM_PRICES_JSON`, una giornata tipica di un
   consulente, poi `uv run python scripts/llm_spend.py --giorni 1`. Da guardare:
   la riga `chat_turn` per specialista e la sua quota in cache. Con il doppio
   conteggio corretto, il numero della chat è quello vero per la prima volta.
2. **Contatore e limiti** (`PROPOSTA.md` §5): `budget.py` nel gateway, piano d'uso
   per consulente, `GET /v1/usage/me`, indicatore nella TopBar.
3. **Strumenti su richiesta per gli specialisti:** `prepare_process_understanding_review`
   e `amend_process_plan` valgono da soli ~13.000 token a passo. Mandarli solo
   nel passo che li usa, o con uno schema ridotto, è la riduzione più grossa
   disponibile. Va misurata con gli eval di qualità del piano, perché cambia
   quello che il modello vede.
4. **Modello per compito** dove lo schema fa il lavoro (`entity_resolution`,
   `retrieval_rerank`, `context_routing`), con gli eval in mano.
5. **Batch/Flex** per i compiti `deferrable` (estrazione delle fonti, playbook, Mem0).

# Piano backend agentico enterprise — stato dei lavori

Documento vivo. Nasce dal confronto con Matryca (ottobre 2026) e dalla lettura
del codice su `main`: DeliR non va riscritto, ma prima di vendere a un'azienda
enterprise servono un confine tenant vero, un runtime che regga più processi,
un tetto di spesa, scritture concorrenti protette, osservabilità; e, dalle
lezioni Matryca, conoscenza derivata servita solo se dimostrata fresca, un
contesto con un budget, valutazioni del comportamento dell'agente.

**A chi serve:** alle sessioni agente (locali e cloud) che portano avanti il
piano, e a Sohayb per sapere dove siamo senza rileggere i diff.

**Come si usa.** Chi riprende il lavoro legge §② e fa quello. Chi lo posa
aggiorna §① (riga dell'intervento), §② (il prossimo passo) e §⑥ (log), nello
stesso commit o nella stessa PR del lavoro.

Ultimo aggiornamento: 2026-10-07.

---

## ① Stato

Stati: **da fare** · **in corso** (con PR) · **fatto** (mergiato) ·
**bloccato** (serve una decisione, §④).

| ID | Intervento | Ondata | Stato |
| --- | --- | --- | --- |
| P2.3 | Ruff (pyflakes, bugbear) su tutto `backend/`; mypy da 21 a 47 moduli | 0 | **fatto** — #53 |
| P0.5 | Versione attesa sulle scritture BPMN: 409 al consulente, conflitto come esito del tool all'agente, base di versione dal canvas, bozza locale con la sua versione, `null` = nessuna versione | 1 | **fatto** — #54 |
| P1.2a | Coda dei confronti: tetto di 5 tentativi, stato `failed` contato | 1 | **fatto** — #55 |
| P1.2b | Quarantena per fonte | 1 | **fatto** (già su main: tentativi per fase, `failed`, errore leggibile, le altre fonti proseguono) |
| — | I `ValueError` dei tool tornano al modello invece di far cadere il turno; argomenti fuori schema gestiti; confini (`RuntimeError`) invariati | 1 | **fatto** — #62 |
| P1.4 | Agent Outcome Harness (stato canonico e derivato prima/dopo, tool chiesti ed eseguiti, scenari stale / tenant / injection / crash) | 1 | **da fare** |
| P0.1 | Identità per persona (JWT), membership, tenant risolto dal server, fine di `default_consultant_id` | 2 | **bloccato** — D1 |
| P0.2 | RLS sul workspace DB | 2 | **bloccato** — dopo D1 |
| P0.3 | Lock dei turni su Postgres per `thread_id`; simulazioni in coda Postgres | 3 | **bloccato** — D2 |
| P0.4 | Tetto di spesa LLM per tenant e ambiente; rate limit API | 3 | **bloccato** — D3 |
| P1.1a | `ProjectionHealth` FRESH / STALE / UNKNOWN; grafo non verificato fresco servito da Postgres (`kg_relation`) | 4 | **fatto** — #56 |
| P1.1b | Watermark per cliente, versione del projector, stato `CORRUPT` dalla riconciliazione (`graph_projection_state`, migrazione canonical 0019) | 4 | **fatto** — #83 |
| P1.3a | Budget in token del prompt di scope (48.000), blocchi con priorità, omissioni dichiarate al modello, XML non duplicato, impronta sha256 | 5 | **fatto** — #61 |
| P1.3b | Riassunto del thread a soglia di token (misurata sulla sola fetta riassumibile, tool call compresi), riassunto del modello validato (vuoto o oltre 2.000 token → estratto), ripiego deterministico solo sui guasti transitori del provider, contato | 5 | **fatto** — #71 |
| P1.3c | Impronta del contesto nel registro dei consumi LLM: colonna `context_fingerprint` (migrazione workspace 0026), la riga `chat_turn` porta l'ultima impronta assemblata nel turno | 5 | **fatto** — #80 |
| P1.5 | Suite security: injection indiretta da PDF/Excel/trascrizioni, cross-tenant, esfiltrazione (job notturno, modello dei test) | 5 | **da fare** |
| P0.6a | Le migrazioni allo startup spegnevano tutti i logger del backend | 6 | **fatto** — #64 |
| P0.6b | Audit log append-only, OpenTelemetry, Sentry, backup con restore provato, cancellazione GDPR end-to-end | 6 | **bloccato** — D4 (infra) |
| P2.1 | Spezzare `memory/gateway.py` e `workspace_database.py` dietro una facciata | 7 | **da fare** |
| P2.2 | `SourceBlobStore`: file originali dietro un'interfaccia, radice assoluta, download a pezzi | 7 | **fatto** — #68 |

---

## ② Prossimo passo

In quest'ordine, senza decisioni da aspettare:

1. **P1.4** Agent Outcome Harness — #84;
2. **P2.1** spezzare `backend/memory/gateway.py` dietro la stessa facciata — #85.

---

## ③ Regole di ingaggio

1. **Un blocco, un branch, una PR.** Branch da `origin/main` aggiornato, in un worktree sotto `.claude/worktrees/` (mai una junction di `node_modules`; `npm ci --prefix frontend` nel worktree). Tanti commit piccoli, uno per passo.
2. **Commit** in italiano, a nome Sohayb Raqaq, **nessun trailer di co-autore**. Il messaggio dice cosa smette di succedere.
3. **Titolo della PR in Conventional Commits** (`type(scope): sommario imperativo`, max 72 caratteri): è un controllo bloccante di CodeRabbit.
4. **CodeRabbit va attivato a mano** con un commento `@coderabbitai review` (il repo ha meno di 10 stelle), e di nuovo dopo ogni push. Ha un limite orario: "Review rate limited" vuol dire riprovare più tardi. A ogni rilievo si risponde nel suo thread con il commit che lo chiude.
5. **Test prima del fix**, rosso senza e verde con. Mai sul DB di sviluppo: niente `.env` copiato nei worktree, niente `--noconftest`, niente `load_dotenv`; `tests/conftest.py` sposta da solo i DSN sullo stack di test (`DELIR_TEST_PG_PORT`, `DELIR_TEST_NEO4J_PORT`). Dove Docker non c'è (sessione cloud), la suite con DB la esegue la CI.
6. **Niente nuovi `# noqa` o `type: ignore`** in `backend/`; testi del frontend sempre via i18next (it, en).
7. **Merge** con `gh pr merge N --merge` (mai `--delete-branch`), poi si rimuovono worktree e branch a mano. Un'altra sessione può mergiare nel frattempo: controllare lo stato prima.
8. **Migrazioni:** prima di aprire la PR, `alembic heads` deve dare una testa sola; il numero di revisione si sceglie guardando `origin/main` aggiornato.

---

## ④ Cosa serve da Sohayb

| ID | Domanda | Raccomandazione | Sblocca |
| --- | --- | --- | --- |
| D1 | Identità: Supabase Auth per persona, o un token per spazio di lavoro? | Supabase: un cliente enterprise chiede SSO e utenti nominali | P0.1, P0.2 |
| D2 | Deploy mono-processo dichiarato, o lock su Postgres per `thread_id`? | Lock Postgres (`pg_advisory_lock`) | P0.3 |
| D3 | Tetto di spesa: euro al mese per tenant e per ambiente | Avviso all'80%, arresto al 100% | P0.4 |
| D4 | VM Oracle (specifica reale) e dominio su Cloudflare | Già in `deployment-and-tenancy.md` §③ | P0.6b, Track A |

---

## ⑤ Trovato fuori perimetro

| Dove | Cosa | Stato |
| --- | --- | --- |
| `migrations_workspace/versions/0026_*` | `0026_usage_context_print` (#80) e `0026_client_sources` (`feat/fonti-cliente`, altra sessione) partono entrambe da `0025`: chi mergia per secondo ripunta la propria `down_revision` | da fare al merge della seconda |
| `e2e/simulation-workspace.spec.ts:381` | "changing run retains the tool…" fallisce a volte su chromium in CI (3 tentativi su 3 il 2026-10-04, verde al rilancio) | instabile, da guardare con chi lavora sulla simulazione |
| Macchina di sviluppo | Con più sessioni, stack Docker e dev server insieme la RAM libera è scesa a 150 MB su 16 GB e Docker Desktop è andato in errore 500 | riavviato; tenere al minimo gli stack di test accesi |

---

## ⑥ Log

| Data | ID | Cosa | Verifica |
| --- | --- | --- | --- |
| 2026-10-07 | P1.1b | #83: `graph_projection_state` (watermark avanzato dal worker nella stessa transazione, `PROJECTOR_VERSION` conservata finche' non si ricostruisce, `corrupt_since`/`corrupt_reason`); `ProjectionHealth.CORRUPT`; `kg_reproject` scrive l'esito | `tests/memory/test_projection_state.py` (11, su Postgres canonical), `tests/memory/test_projection_health.py`; migrazione 0019 su e giu' |
| 2026-10-07 | P1.3c | #80: `context_fingerprint` nel registro dei consumi; `build_scope_system_prompt` annota l'impronta in un raccoglitore del turno (ContextVar, arriva ai nodi LangGraph), il runtime la passa alla riga `chat_turn` | `tests/agents/test_context_fingerprint_trace.py`, `test_the_ledger_row_reaches_postgres`; migrazione 0026 su e giù su Postgres locale |
| 2026-10-07 | P1.3b | #71: i 6 rilievi CodeRabbit chiusi — tool call nel conto dei token, soglia sulla sola fetta riassumibile, ripiego solo su `TRANSIENT_PROVIDER_ERRORS` (log error, `degradation_counters`), messaggi senza id non riassunti due volte, test su vuoto, giro ripetuto e confini; dal controllo pre-merge, il riassunto del modello validato (`ThreadSummary`, Pydantic) prima di entrare nello stato, un tetto al riassunto con ripieghi consecutivi, gli esiti dei tool fuori dall'estratto | `tests/agents/test_thread_summary.py`: 22 verdi; `tests/agents` + `tests/llm`: 527 verdi |
| 2026-10-06 | P2.2 | #68: download a pezzi, radice relativa ancorata al progetto, nome file verificato (rilievi CodeRabbit) | `tests/workspace/test_blob_store.py`, `tests/evidence/test_source_ingestion.py`: 26 verdi |
| 2026-10-06 | — | #62 mergiata: i `ValueError` dei tool tornano al modello; istruzione esplicita di non riportare al consulente nomi di tool, id o messaggi tecnici | `tests/agents/test_tool_errors.py` |
| 2026-10-04 | P0.6a | #64 mergiata: `ensure_schema` non riconfigura più i log; `env.py` non spegne i logger esistenti | `tests/server/test_logging_survives_migrations.py`, rosso senza il fix |
| 2026-10-04 | P1.3a | #61 mergiata: budget in token del prompt di scope | `tests/agents/test_context_budget.py` |
| 2026-10-04 | P0.5 | #54 mergiata: scritture BPMN concorrenti | `tests/bpmn/test_bpmn_concurrent_writes.py`, 15 test |
| 2026-10-04 | P1.1a, P1.2a | #56 e #55 mergiate | `tests/memory/test_projection_health.py`, `tests/conformance/test_conformance_queue.py` |
| 2026-10-04 | P2.3 | #53 mergiata | ruff e mypy puliti, 1700 test verdi |
| 2026-10-03 | — | Analisi della codebase e piano in 8 ondate | questo documento |

# Pipeline delle fonti: dove siamo e come riprendere

Stato al 7 ottobre 2026. Serve a chi riprende il lavoro da un'altra sessione
(cloud, da telefono): cosa c'e' gia', cosa manca e in che ordine farlo.

## Dove seguire il lavoro

| cosa | dove |
| --- | --- |
| Il piano, con lo stato delle attivita' e il registro | [DeliR - Piano di lavoro e avanzamento](https://claude.ai/code/artifact/7fc09e95-b508-4fe4-9d98-e492c0598604) |
| L'architettura delle modalita' e della pipeline di ingestione | [DeliR - Architettura delle modalita' di lavoro](https://claude.ai/code/artifact/f4844720-0814-4e12-89ac-5ff5e7bd471d) |
| I blocchi in corso | #72 (backend), #75 (pannello Fonti), #81 (chat), #82 (pagina del cliente) |

Il piano su claude.ai e' la fonte di verita': dopo ogni blocco mergiato si
aggiornano "Adesso", la riga dell'attivita' in "Piano di lavoro" e una riga del
"Registro", con data e numero di PR. Si modifica solo con il connettore Claude
Docs. **Gia' indietro:** mancano le righe di registro per la #72 e la #75.

## Cosa c'e' (su main)

| PR | attivita' | cosa |
| --- | --- | --- |
| #32, #36, #38, #44 | P1.10-P1.11, P1.15 | caricamento in background, Evidence Bucket con ancore, conferma del consulente, `+` nelle chat |
| #50 | P1.12 | affermazioni estratte alla conferma o all'invio in chat, ognuna legata alla porzione che la sostiene |
| #52 | P1.14 | le affermazioni nel grafo: `Source -HAS_EVIDENCE-> Evidence -SUPPORTS-> Claim` |
| #60 | P1.13 | confronto fra i file del processo; ogni conflitto si vede con le due evidenze, nel grafo e' una `Contradiction` fra i due Claim |

## Cosa manca, in ordine

| # | lavoro | stato |
| --- | --- | --- |
| 1 | **#72**, backend delle fonti del cliente (P1.16 1/4) | 4 rilievi CodeRabbit corretti il 7 ottobre (progetto mancante, tetto al confronto, cliente canonical condiviso, vincoli ORM); poi CI verde e merge |
| 2 | **#75**, pannello Fonti (P1.16 2/4) | completa: test, screenshot desktop e mobile; CodeRabbit, CI e merge dopo la #72 |
| 3 | **#81**, chat del consulente (P1.16 3/4): "Tutto il cliente" in "Dove va questo file?" | pronta, impilata su #75 (`feat/fonti-cliente-chat`) |
| 4 | **#82**, pagina del cliente con le sue fonti e ricerca globale (P1.16 4/4) | pronta, impilata su #81 (`feat/fonti-cliente-pagina`) |
| 5 | Nodi Episode delle interviste nel grafo (resto di P1.14) | da fare |
| 6 | Chiudere un conflitto dalla UI: scegliere quale vale, con una nota (resto di P1.13) | da fare |
| 7 | I piani dei processi che leggono anche le fonti del cliente | da decidere con Sohayb |

### #75, pannello Fonti: fatto

- `useUploadClientSourceMutation` in `frontend/src/features/projects/api.ts`:
  dopo il caricamento rilegge le Fonti di tutti i progetti in cache.
- `ProjectDetailPage.tsx` passa a `SourcesPanel` il cliente del progetto.
- Nel menu "Ambito" la prima voce e' "Tutto il cliente «nome»"; nella lista una
  fonte del cliente dice "Tutto il cliente"; nel dettaglio "Vale per: Tutto il
  cliente «nome»", senza processo da aprire.
- Test vitest del pannello e dell'hook; screenshot Playwright desktop e mobile
  con API finte (spec temporaneo, non committato). Lo screenshot mobile ha
  mostrato il form di caricamento che sbordava: corretto.

### #81 e #82: cosa c'e'

- **#81**: in "Dove va questo file?" il menu "Ambito" ha "Tutto il cliente «nome»";
  la destinazione porta `clientId`, il file va a
  `POST /v1/workspace/clients/{id}/sources/upload`, e la chat ne legge lo stato
  dalle Fonti del progetto scelto.
- **#82**: pagina `/clients/:clientId` con le fonti del cliente (lo stesso
  `SourcesPanel`, con `projectId: null`); la ricerca globale trova le fonti del
  cliente e porta li', come per il cliente stesso; "Apri scheda" dalla lista
  clienti.
- Le due PR sono impilate: dopo ogni merge la successiva passa a `main`
  (merge di `main` nel branch, base cambiata a mano).

## Come funzionano le fonti del cliente (backend, #72)

- `workspace_sources.client_id` sempre pieno; `project_id` vuoto per le fonti
  del cliente (migrazione workspace `0026_client_sources`).
- `POST /v1/workspace/clients/{id}/sources/upload`,
  `GET /v1/workspace/clients/{id}/sources`.
- `list_project_sources(..., include_client=True)` per il pannello Fonti e il
  contesto degli agenti. Il default resta il solo progetto: il set di fonti dei
  piani non legge le fonti del cliente, e confermarne una non rimette in coda i
  piani.
- Una fonte di progetto si confronta anche con quelle del cliente; nel grafo una
  fonte del cliente entra con `scope.resolve_client`, senza progetto.
- Eliminare un progetto lascia le fonti del cliente; eliminare il cliente le
  toglie dal workspace e dal grafo (`erase_client_sources`).

## Regole di lavoro

- Un branch per blocco, tanti commit piccoli, PR, CI verde, merge su main senza
  `--delete-branch` (poi il branch remoto si cancella a mano), e subito un
  branch nuovo per il blocco dopo.
- Prima di ogni blocco: stato dei branch rispetto a main. Le PR aperte da altre
  sessioni non si toccano.
- Commit a nome Sohayb Raqaq, **senza** trailer `Co-Authored-By`; descrizioni
  delle PR senza "Generated with Claude Code".
- Titolo della PR in Conventional Commits, `type(scope): sommario` (max 72).
  CodeRabbit non parte da solo: commento `@coderabbitai review`, e di nuovo dopo
  ogni push. Ha un limite orario: se risponde "rate limited", si riprova dopo.
- Dopo ogni commit `git status --short` vuoto. Prima di pushare una migrazione,
  `alembic heads` con una testa sola su `alembic.ini` e `alembic_workspace.ini`:
  le altre sessioni aggiungono migrazioni su main.
- I test non toccano mai il database di sviluppo: niente `.env` copiato nei
  worktree, niente `load_dotenv`, niente `--noconftest`.
- Nei test i modelli sono finti; OpenAI resta per la produzione e le prove a
  mano.
- Nel cloud non ci sono Postgres e Neo4j: per i test che li vogliono giudica la
  CI della PR, e lo si dice.

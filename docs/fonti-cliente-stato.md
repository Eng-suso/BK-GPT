# Pipeline delle fonti: dove siamo e come riprendere

Stato al 7 ottobre 2026. Serve a chi riprende il lavoro da un'altra sessione
(cloud, da telefono): cosa c'e' gia', cosa manca e in che ordine farlo.

## Dove seguire il lavoro

| cosa | dove |
| --- | --- |
| Il piano, con lo stato delle attivita' e il registro | [DeliR - Piano di lavoro e avanzamento](https://claude.ai/code/artifact/7fc09e95-b508-4fe4-9d98-e492c0598604) |
| L'architettura delle modalita' e della pipeline di ingestione | [DeliR - Architettura delle modalita' di lavoro](https://claude.ai/code/artifact/f4844720-0814-4e12-89ac-5ff5e7bd471d) |
| Il blocco in corso | PR #75, questo branch (`feat/fonti-cliente-pannello`) |

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
| 1 | **#72**, backend delle fonti del cliente (P1.16 1/4) | CI verde; manca CodeRabbit (`@coderabbitai review`), poi merge |
| 2 | **#75**, pannello Fonti (P1.16 2/4) | in corso, vedi sotto |
| 3 | Chat del consulente (P1.16 3/4): la voce "Tutto il cliente" in "Dove va questo file?" | da fare, branch nuovo da main |
| 4 | Pagina del cliente con le sue fonti, e la ricerca globale che le trova (P1.16 4/4) | da fare, branch nuovo da main |
| 5 | Nodi Episode delle interviste nel grafo (resto di P1.14) | da fare |
| 6 | Chiudere un conflitto dalla UI: scegliere quale vale, con una nota (resto di P1.13) | da fare |
| 7 | I piani dei processi che leggono anche le fonti del cliente | da decidere con Sohayb |

### #75, pannello Fonti: cosa resta

Il primo commit c'e': `useUploadClientSourceMutation` in
`frontend/src/features/projects/api.ts`. Resta:

1. `ProjectDetailPage.tsx` passa a `SourcesPanel` il cliente del progetto
   (`project.clientId`, e `project.client` per il nome).
2. In `SourcesPanel.tsx`, nel menu "Ambito" della finestra di caricamento, la
   prima voce e' `client:<clientId>`: "Tutto il cliente «nome»". Scelta quella,
   il caricamento usa `useUploadClientSourceMutation`.
3. Nella lista, una fonte con `projectId === null` dice che vale per tutto il
   cliente.
4. Nel dettaglio, al posto di "Processo collegato" una riga "Vale per: tutto il
   cliente «nome»", e niente "Apri processo collegato".
5. Testi it/en in `frontend/src/locales/*/projects.json`; test vitest del
   pannello e dell'hook; screenshot Playwright desktop e mobile con API finte
   (spec temporaneo, non si committa).

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

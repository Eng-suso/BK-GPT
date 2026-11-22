# Milestone 01 — Audit Docker e servizi locali

Data: 2026-11-18. Ambito: configurazione nel repository e verifiche statiche. Stato dei container e build runtime non verificati: il client Docker è installato, ma questa sessione non può accedere al daemon.

## Inventario

| Configurazione | Servizi | Scopo |
| --- | --- | --- |
| `ops/docker-compose.yml` | PostgreSQL con pgvector, Neo4j con APOC, Docling | Stack dati e documenti locale; porte legate a `127.0.0.1`; volumi persistenti per PostgreSQL e Neo4j. |
| `ops/docker-compose.test.yml` | PostgreSQL, Neo4j | Test con porte separate e dati in `tmpfs`; riusa gli script di inizializzazione PostgreSQL. |
| `ops/docker-compose.prod.yml` insieme al file base | I tre servizi base, runner Prosimos, app FastAPI con frontend compilato | Overlay di produzione; app e Prosimos costruiti da Dockerfile locali, limiti di memoria per tutti e cinque i servizi. |

L'immagine dell'app è multistadio: `npm ci` e build Vite, `uv sync --locked` per Python, runtime non root con frontend statico. L'entrypoint applica le migrazioni canonical e workspace sotto advisory lock e avvia un solo worker Uvicorn. `/health/ready` controlla i due database e le revisioni Alembic. I file `.env` sono esclusi dal contesto Docker e ignorati da Git.

## Esito delle verifiche

- `docker compose config --quiet` passa per stack base, test e base + overlay produzione usando `ops/.env.example`.
- I 10 controlli di `tests/server/test_prod_compose.py` passano con `pytest --noconftest`: limiti di memoria (11 GiB complessivi), binding locale, autenticazione, migrazioni e worker singolo. Il normale avvio di pytest è bloccato dalla fixture globale perché lo stack di test non è acceso.
- Con l'attuale `ops/.env`, `docker compose ...prod.yml config --quiet` fallisce: manca `DELIR_TENANT_ID`. Il file locale contiene le variabili dello stack dati, ma non tutte quelle dell'app. Nessun valore segreto è stato letto o riportato nell'audit.
- `docker info` fallisce per accesso negato al daemon. Non sono stati eseguiti `build`, `up`, health check runtime o smoke test dell'immagine.

## Rilievi ordinati per priorità

1. **Alta — prova locale non isolata.** L'overlay di produzione riusa `container_name` e i nomi espliciti dei volumi del compose base. `-p` cambia il nome del progetto Compose, ma non isola questi nomi né le porte host predefinite. Una prova sulla macchina di sviluppo può collidere con lo stack esistente o riusarne i dati. `ops/README.md` avverte del problema, ma non fornisce un profilo locale pronto all'uso.
2. **Alta — configurazione di rilascio incompleta.** L'`ops/.env` attuale non soddisfa l'overlay. `ops/.env.example` include i campi richiesti, ma i valori dimostrativi non sono adatti a un avvio reale. Manca una procedura locale che generi e validi la configurazione necessaria senza copiare segreti nel repository o nei log.
3. **Media — nessun gate dell'immagine completa.** La CI avvia i servizi dati e testa backend, frontend e runner separatamente; non costruisce l'immagine applicativa né verifica il percorso combinato `build → migrazioni → /health/ready`. Un errore di Dockerfile o di packaging può quindi superare i test correnti.
4. **Media — immagini esterne non immutabili.** PostgreSQL, Neo4j, Docling, Node, Python e `uv` sono riferiti tramite tag, senza digest. `uv.lock` e i lockfile npm aiutano a riprodurre le dipendenze, ma un rebuild successivo può usare immagini base diverse.
5. **Media — readiness parziale.** La readiness dell'app misura PostgreSQL e le revisioni, non Neo4j, Prosimos o Docling. L'app attende Neo4j e Prosimos sani solo all'avvio; per Docling attende soltanto `service_started`. Un container app `healthy` non prova che documenti e simulazioni siano operativi.
6. **Bassa — documentazione divergente.** `ops/.env.example` indica di copiarlo in `ops/postgres/.env`, mentre Compose legge `ops/.env`. Il documento `docs/deployment-and-tenancy.md` contiene ancora una descrizione precedente secondo cui non esiste il Dockerfile dell'app; la sezione aggiornata di `ops/README.md` è più affidabile.

## Criterio per chiudere Milestone 01

Preparare un overlay locale isolato per nomi, volumi e porte; aggiungere una validazione della configurazione senza esporre valori; costruire app e runner; avviare lo stack isolato con `--wait`; verificare `/health/ready` e almeno una chiamata minima a Neo4j, Docling e Prosimos; registrare versioni o digest delle immagini e i comandi di teardown che agiscono solo sullo stack isolato. Finché il daemon non è accessibile, questi controlli runtime restano da eseguire.

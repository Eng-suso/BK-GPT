# Stack locali isolati: STAGING e PROD-SIM

DEV continua a usare `ops/docker-compose.yml` e l'attuale `ops/.env`, senza
modifiche a container, porte o volumi esistenti. Lo stack pytest in
`docker-compose.test.yml` resta separato e temporaneo. STAGING e PROD-SIM
riusano il compose base e l'overlay applicativo di produzione, poi applicano
`docker-compose.staging.yml` per nomi, volumi e budget locali. Nessun servizio
nuovo e nessuna modifica alla produzione reale.

Dal root del repository, i comandi quotidiani sono `npm run env:dev`,
`npm run env:staging` e `npm run env:prod-sim`. Per fermare gli ultimi due senza
perdere dati: `npm run env:staging:stop` e `npm run env:prod-sim:stop`.
`npm run dev` rimane disponibile quando i dati DEV sono già avviati.
In PowerShell su Windows, usare `npm.cmd run ...` se la policy blocca `npm.ps1`.

## Accesso al browser nei tre ambienti

- DEV: apri l'indirizzo frontend stampato da `npm run env:dev` (di norma
  `http://127.0.0.1:3030/`). L'API locale usa la porta stampata dallo script
  (di norma 8000); in DEV l'autenticazione e' disattivata.
- STAGING: apri `http://127.0.0.1:18000/`. Alla prima visita inserisci il
  `DELIR_DEFAULT_TENANT_ID` e il `DELIR_API_TOKEN` del file ignorato
  `ops/.env.staging`.
- PROD-SIM: apri `http://127.0.0.1:28000/` e usa le stesse due chiavi, ma
  esclusivamente dal file ignorato `ops/.env.prod-sim`.

Il token inserito resta nella `sessionStorage` dell'origine del browser: le
porte 18000 e 28000 hanno sessioni separate. Il frontend prova l'identita'
prima di caricare le richieste del workspace. Non mettere questi token in
`VITE_*` o nel codice. La trascrizione audio live invia tenant e token nel primo
messaggio WebSocket, dopo l'apertura della connessione; l'URL non li contiene.
Il server verifica entrambi prima di collegarsi al provider. STAGING e PROD-SIM usano inizialmente un
placeholder per `OPENAI_API_KEY`: le verifiche locali non fanno chiamate LLM.
Se configuri chiavi provider reali, usane una dedicata per ambiente; il
validatore rifiuta il riuso fra STAGING, PROD-SIM e il `.env` di DEV usato da
FastAPI. Il consumo LLM e' registrato nel database separato di ciascuno stack.

| Ambiente | Project name | Volumi | Porte host (Postgres, Neo4j HTTP/Bolt, Docling, app) | Limite massimo full stack |
| --- | --- | --- | --- | --- |
| DEV | `ops` | `delir_pgdata`, `delir_neo4jdata` | 5432, 7474, 7687, 5001, app 8000 se usata | dati locali, senza limiti Compose |
| STAGING | `delir-staging` | prefisso `delir_staging_` | 15432, 17474, 17687, 15001, 18000 | 8 GiB |
| PROD-SIM | `delir-prod-sim` | prefisso `delir_prod_sim_` | 25432, 27474, 27687, 25001, 28000 | 8 GiB |

Le reti default di Compose portano il project name. Non ci sono reti o volumi
`external`. L'overlay assegna nomi espliciti distinti anche se qualcuno passa
un project name sbagliato. Le password di STAGING e PROD-SIM vengono generate
separatamente in `ops/.env.staging` e `ops/.env.prod-sim`, ignorati da Git ed
esclusi dal contesto Docker. Il validatore controlla presenza, identità dello
stack, porte, formato dei segreti, sovrapposizioni con DEV e tra i due stack
locali, senza stampare i valori. Il validatore estende la classe
`backend.settings.Settings` con campi Compose tipizzati da Pydantic e usa
`SecretStr` per mascherare le credenziali nelle rappresentazioni. La generazione
resta affidata a `secrets`; `SecretStr` non cifra i file e non sostituisce un
Secret Manager. L'overlay locale forza tracing LangSmith spento e svuota chiave
LangSmith e token admin anche se la shell contiene questi valori. Le altre
variabili Compose che la shell sovrascriverebbe sono rifiutate dal validatore.
Non eseguire `docker compose config` senza
`--quiet`: l'output completo contiene le credenziali interpolate.

## STAGING: avvio selettivo e full stack

In PowerShell, prepara il virtualenv dal root con
`uv --cache-dir .uv-cache sync --locked`, poi entra nella cartella `ops`:

```powershell
& ..\.venv\Scripts\python.exe local_release.py init staging     # solo al primo avvio; non sovrascrive
& ..\.venv\Scripts\python.exe local_release.py check staging

# Solo database e grafo, per lavoro senza app/Docling/Prosimos:
& ..\.venv\Scripts\python.exe local_release.py data-up staging

# Full stack, solo quando serve il percorso completo:
& ..\.venv\Scripts\python.exe local_release.py up staging
```

Non tenere DEV, STAGING e PROD-SIM full stack accesi insieme su un PC con RAM
limitata. Il budget STAGING/PROD-SIM è: PostgreSQL 1 GiB, Neo4j 1.5 GiB,
Docling 3 GiB, Prosimos 1 GiB, app 1.5 GiB. Si tratta di limiti, non di una
prenotazione di RAM. Con dati o documenti grandi, i limiti locali potrebbero
richiedere una revisione misurata. Avviare solo `postgres neo4j` richiede al
massimo 2.5 GiB dei limiti configurati.

## Verifica runtime

Eseguire dopo il full stack, sempre da `ops`. `/health/ready` verifica che le
migrazioni canonical e workspace siano alle revisioni attese. I tre smoke test
usano gli endpoint e il driver già presenti nel repository; non inviano token
o password in output.

```powershell
(Invoke-WebRequest http://127.0.0.1:18000/health/ready).StatusCode
docker compose -p delir-staging --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml exec -T app python -c 'import os; from neo4j import GraphDatabase; d=GraphDatabase.driver(os.environ["NEO4J_URL"], auth=("neo4j", os.environ["NEO4J_PASSWORD"])); print(d.execute_query("RETURN 1 AS ok").records[0]["ok"]); d.close()'
docker compose -p delir-staging --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml exec -T app python -c 'import urllib.request; print(urllib.request.urlopen("http://docling:5001/health", timeout=10).status)'
docker compose -p delir-staging --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml exec -T app python -c 'import urllib.request; print(urllib.request.urlopen("http://prosimos:5000/health", timeout=10).status)'

# Manifest locale senza stampare variabili interpolate o segreti:
docker compose -p delir-staging --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml config --hash '*'
docker compose -p delir-staging --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml images
```

`OPENAI_API_KEY=local-no-provider-calls` è un placeholder generato: questi
smoke test non richiedono un provider. I worker delle code sono spenti nello
stack locale per evitare chiamate LLM non intenzionali. Le funzionalità AI
richiedono una credenziale di staging dedicata, inserita solo nel file ignorato,
e una verifica separata dei costi. L'API è autenticata; `/health/ready` è
pubblica. `DELIR_DEFAULT_TENANT_ID` e `DELIR_ALLOWED_TENANT_IDS` sono
configurati separatamente: il default serve richieste senza header tenant e
deve comparire nella allowlist; la allowlist può contenere più tenant. Il
vecchio `DELIR_TENANT_ID` resta solo come fallback compatibile nel compose del
pilota. Questo non costituisce una soluzione completa di identità multi-tenant.

## Stop e teardown esclusivi dello STAGING

Lo script riesegue `check` e verifica il project name, tutti i nomi di
container/volumi/rete e le porte Compose prima di agire. `stop` conserva i tre
volumi staging. `teardown` invoca `down -v` **solo** sul progetto staging e
rimuove i suoi tre volumi. Non usare comandi Compose manuali con `-p ops` per
operare lo staging.

```powershell
& ..\.venv\Scripts\python.exe local_release.py stop staging

# Solo quando vuoi eliminare i dati STAGING:
& ..\.venv\Scripts\python.exe local_release.py teardown staging
```

Per PROD-SIM, `& ..\.venv\Scripts\python.exe local_release.py init prod-sim`
genera una configurazione distinta. Dopo aver costruito e verificato STAGING,
`& ..\.venv\Scripts\python.exe local_release.py up prod-sim` promuove le stesse
immagini app e Prosimos tramite `docker tag` e avvia PROD-SIM con `--no-build`:
le configurazioni e i dati cambiano, la build applicativa resta identica.
`stop prod-sim` e `teardown prod-sim` agiscono solo sul suo progetto. Anche
PROD-SIM va avviato selettivamente. Il file locale può essere rigenerato solo
dopo aver distrutto il relativo stack: su un volume PostgreSQL esistente,
cambiare password nel file non aggiorna le password dei ruoli inizializzati.

## Criteri di accettazione

1. `\.venv\Scripts\python.exe -m pytest --noconftest tests/server/test_local_release_compose.py`
   passa: risorse e porte DEV/STAGING/PROD-SIM disgiunte, nessuna risorsa
   `external`, validatore che rifiuta conflitti e configurazione incompleta.
2. `docker compose ... config --quiet` passa per lo staging con file generato.
3. Con daemon accessibile: build e `up --wait` riescono; l'app è healthy,
   `/health/ready` risponde 200, i tre smoke test passano.
4. Annotare uno stato DEV prima e dopo `down -v` STAGING (container, volumi,
   disponibilità del database): DEV deve essere identico e il suo volume deve
   conservare i dati. Questo test runtime non è sostituibile dal test statico.
5. `up prod-sim` promuove le immagini app e Prosimos già provate in STAGING;
   verificare che gli ID immagine dei due ambienti coincidano e che readiness,
   database e smoke test passino anche con la configurazione PROD-SIM.

Esito della verifica del 2026-11-18: [evidenza e ID immagini](../docs/release/milestone-01-staging-evidence.md).

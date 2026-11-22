# Milestone 01 — STAGING locale: evidenza di accettazione

Data: 2026-11-18. Ambiente: Docker Engine 28.3.2, Compose 2.39.1 su PC locale.
Il progetto DEV era già attivo; non è stato fermato o modificato. Il working
tree conteneva modifiche preesistenti al frontend e alla CI, quindi l'ID immagine
è il riferimento esatto della build locale, non il solo commit Git.

## Risultato

| Verifica | Esito osservato |
| --- | --- |
| Compose base + prod + staging | `config --quiet` riuscito; project `delir-staging`, cinque container con prefisso staging, rete `delir-staging_default`, tre volumi `delir_staging_*`, porte host 15432/17474/17687/15001/18000. Nessuna risorsa `external`. |
| Build e avvio | `up -d --build --wait --wait-timeout 600` riuscito; PostgreSQL, Neo4j, Docling, Prosimos e app `healthy`. |
| Migrazioni | `/health/ready` HTTP 200, `workspace: ok`, `canonical: ok` sia al primo avvio sia dopo ricreazione da volumi vuoti. |
| Integrazioni | Query Neo4j `RETURN 1` → `1`; `GET http://docling:5001/health` → 200; `GET http://prosimos:5000/health` → 200, chiamati dal container app. |
| Isolamento dati | Tabella sintetica `local_release_isolation_probe` creata solo in PostgreSQL STAGING; `to_regclass(...) IS NULL` su DEV → `true`. Nessun dato cliente usato. |
| Teardown | `down -v` su `delir-staging` ha rimosso solo container, rete e tre volumi staging. Il progetto DEV è rimasto `running healthy`; i volumi `delir_pgdata` e `delir_neo4jdata` hanno mantenuto nome e data di creazione. Impronta del catalogo database DEV invariata prima e dopo. |
| Ricreazione | `up -d --wait --wait-timeout 600` su volumi nuovi riuscito; app `healthy`, readiness 200. |
| Comandi protetti | `local_release.py teardown staging` ha rimosso solo STAGING; DEV ancora sano con impronta e identità dei volumi invariati. `local_release.py up staging` ha ricostruito le immagini, creato volumi nuovi e portato l'app a `healthy`; readiness 200. `local_release.py stop staging` riuscito. |
| Test automatici | 16 test passati (`test_local_release_compose.py` + `test_prod_compose.py`, con `--noconftest` per evitare la fixture del data stack pytest), Ruff passato. |

Il secondo avvio ha usato l'overlay finale che imposta `LANGSMITH_TRACING=false`,
`LANGSMITH_API_KEY` e `DELIR_ADMIN_TOKEN` vuoti. Anche con variabili LangSmith
presenti nella shell, il `config` risolto mostrava solo i valori locali forzati.
Nessun valore di password o token è stato stampato nell'evidenza.

## Immagini e configurazione effettiva

ID immagine dei container avviati nel test finale:

| Servizio | ID immagine |
| --- | --- |
| PostgreSQL | `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` |
| Neo4j | `sha256:037cf5756f0135cbfd66b739b6df7c7c4bb100f9ce11602f6f9538e17e02c74d` |
| Docling | `sha256:79e5fcd19ab227ed36323fa5fa31820d14d53efc4f073417ba37be7931c7af0a` |
| Prosimos | `sha256:d78213ad587381a369a87acf3895eaff4dff0d6935a2ef693d5bfcd95858c96c` |
| App | `sha256:ffacf5cba1651a0adc80f83427b45b8e552873cfa5e26df73a55b34a7a57d6eb` |

Hash della configurazione risolta, ottenuti con `docker compose ... config --hash '*'`
senza esporre la configurazione interpolata:

| Servizio | Hash |
| --- | --- |
| app | `a0331b42fdd9c2b5bb8da3a7a784f04dd75ea36c9afc75cbd40d494d4d6fae34` |
| docling | `970166707283ad46273c1c0dfeea5154ea5dda150ff88a7f58a88f272d1495a6` |
| neo4j | `fd75fb9884cfe32ab802788bc196f1fdcbae6bccfcede81d5ce071e38e03fd78` |
| postgres | `a872cc69e184dc1b1c85309aef5d99f1c3c8f76884dfcad3fa7036cbbe1c1248` |
| prosimos | `cce9b2f3d47a81ed59cb2382918755ef0224916e0e3c935c3a92dd28d1f66e75` |

Lo stack staging è stato **fermato** dopo i test per liberare RAM; i volumi
staging dell'ultimo avvio sono conservati. I volumi DEV restano intatti.

## PROD-SIM: prova runtime della stessa build

Con STAGING fermo, `local_release.py init prod-sim` ha generato una
configurazione con credenziali e porte proprie. Il primo avvio PROD-SIM ha
portato tutti e cinque i servizi a `healthy`; `/health/ready` ha risposto 200
con `workspace: ok` e `canonical: ok`. La query Neo4j `RETURN 1` ha restituito
`1`; gli endpoint `/health` di Docling e Prosimos hanno risposto 200.

Un marcatore sintetico è stato scritto solo nel database PROD-SIM; una query
in sola lettura su DEV ha confermato che la tabella non esiste lì. La
ricreazione dei container PROD-SIM ha conservato il marcatore nel volume
PROD-SIM. DEV è rimasto `running healthy` durante la prova.

Per assicurare la **stessa build applicativa**, `local_release.py up prod-sim`
ora promuove le immagini già verificate in STAGING con `docker tag` e avvia
Compose con `--no-build --force-recreate`. Gli ID osservati dei container
STAGING e PROD-SIM coincidono:

| Immagine | ID in entrambi gli ambienti |
| --- | --- |
| App | `sha256:ffacf5cba1651a0adc80f83427b45b8e552873cfa5e26df73a55b34a7a57d6eb` |
| Prosimos | `sha256:d78213ad587381a369a87acf3895eaff4dff0d6935a2ef693d5bfcd95858c96c` |

Gli hash della configurazione Compose di PROD-SIM sono distinti da STAGING:
app `f0af7c72db607601065a38d241b956a1564af92a60d260d8b845ab9ff6332738`,
PostgreSQL `1e3deb8863bd0392fa604284e4631e7535c008f126585a6faba70813e70e7c1d`,
Neo4j `cd746eb8b3ff76407de2aa09fccc4f6d82c7b8e6b08c58d233`,
Docling `0b6fa5c6a9f677e41fbe29cbf2edb9dc088bff6c548429a632956aa6549f809f`,
Prosimos `b7e225d48156fd758529ef666626b6103a8fb5b5102d14a366c7391e4d0beabc`.

PROD-SIM è stato **fermato** al termine della prova per risparmiare RAM; i
suoi volumi restano separati da quelli DEV e STAGING.

I nuovi comandi npm sono stati verificati il 2026-11-18 con `npm.cmd run
env:staging`, `npm.cmd run env:staging:stop`, `npm.cmd run env:prod-sim` e
`npm.cmd run env:prod-sim:stop`: tutti sono riusciti. `env:dev` usa il launcher
DEV già esistente; la configurazione Compose DEV è valida, ma il launcher non
è stato riavviato durante questa prova per non interrompere processi DEV in
uso.

## Limiti e prossimi passi

- I test verificano salute e connettività, non una simulazione completa o un
  documento reale. Con i limiti RAM locali, carichi grandi possono richiedere
  una misura e una regolazione.
- Le immagini esterne nel Compose sono ancora referenziate da tag mutabili.
  Gli ID sopra identificano la prova eseguita, ma un rebuild futuro potrebbe
  usare un'immagine base diversa. Gli ID di app e Prosimos sono cambiati tra
  la prima build e la build finale, quindi questa prova non dimostra identità
  binaria tra rebuild. Per un rilascio ripetibile tra macchine, fissare digest
  e produrre un manifest della build.
- Il placeholder OpenAI rende sicuri gli smoke test senza provider. Le funzioni
  AI necessitano di una credenziale staging dedicata e di un test separato.
- `SecretStr` maschera i valori in Python; il file locale `.env` non è cifrato.
  La custodia dei segreti di produzione resta un'attività separata.

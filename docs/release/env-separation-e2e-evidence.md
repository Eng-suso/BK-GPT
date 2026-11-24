# Separazione DEV / STAGING / PROD-SIM — verifica E2E

Data: 2026-11-24. Docker Engine 28.3.2 su PC locale con 7.6 GiB assegnati a
Docker. Completa la [verifica del 2026-11-18](milestone-01-staging-evidence.md),
che copriva salute, connettività e isolamento dei volumi, con le prove su
credenziali, accesso dal browser e dati visti dall'app. Nessun valore segreto
compare in questo documento o nell'output degli script.

## Come è stata eseguita

- Lo stack DEV (data stack `ops`) è rimasto acceso per tutta la prova.
- Prima PROD-SIM era già acceso. Poi PROD-SIM è stato fermato con
  `local_release.py stop` ed è stato acceso STAGING. Alla fine STAGING è stato
  fermato e PROD-SIM riacceso. Due full stack insieme non stanno nella RAM.
- STAGING è stato acceso con `up --no-build --pull never`, senza
  `local_release.py up`: quel comando ricostruisce dal working tree, che
  conteneva modifiche non committate di altri lavori. Entrambi gli stack hanno
  girato con la stessa immagine app
  `sha256:2b5ac4f30c0fa592dcfe550c67ca94d49b844d2963cebcca0d16acffa289a9cf`.
- Script: `ops/verify_env_isolation.py` e `ops/verify_auth_gate.mjs` (vedi
  [ops/local-release.md](../../ops/local-release.md)).

## Risultati

| Verifica | STAGING | PROD-SIM |
| --- | --- | --- |
| Test statici Compose (`test_local_release_compose.py`, `test_prod_compose.py`) | 17/17 | (stessi test) |
| `local_release.py check` | valida | valida |
| `/health/ready` | 200 | 200 |
| API senza token | 401 | 401 |
| API con token e tenant propri | 200 | 200 |
| API con il token dell'altro stack | 401 | 401 |
| API con il tenant dell'altro stack | 403 | 403 |
| API con il tenant DEV `local` | 403 | 403 |
| PostgreSQL `delir_app` con password DEV / dell'altro stack / inventata | rifiutata | rifiutata |
| Neo4j con password DEV / dell'altro stack | rifiutata | rifiutata |
| Token API, password DB, Neo4j, superuser diversi nei tre file | sì | sì |
| Docling e Prosimos `/health` dall'app | 200 / 200 | (healthy) |
| Ambiente dentro il container | `staging`, auth on, LangSmith off, admin token vuoto | idem con `prod-sim` |
| Script API (`verify_env_isolation.py`) | 18/18 | 18/18 |
| E2E browser (`verify_auth_gate.mjs`) | 10/10 | 10/10 |

L'E2E browser verifica nell'ordine:
- senza credenziali si vede il form di accesso;
- il token e il tenant dell'altro stack vengono rifiutati e la pagina resta bloccata;
- con le credenziali proprie si apre il workspace (Progetti, tenant mostrato in alto) senza nessun 401 o 403;
- la sessione resta dopo un reload;
- un nuovo contesto browser torna bloccato;
- il token non compare in `localStorage`, negli URL delle richieste né nei 47 bundle JS serviti.

### Isolamento dei dati visto dall'app

Su STAGING è stato creato via API il cliente sintetico
`zz-probe-isolamento-2026-11-24`. Era visibile su STAGING, assente su PROD-SIM
(via API) e assente su DEV (lettura del DB workspace DEV). Il cliente resta nel
volume STAGING: non contiene dati reali.

### DEV non toccato

L'elenco dei container è identico prima e dopo la prova. I volumi
`delir_pgdata` e `delir_neo4jdata` hanno la stessa data di creazione
(2026-09-01). `delir-postgres` e `delir-neo4j` sono rimasti `healthy`.

## Cose emerse

1. **`DELIR_ADMIN_TOKEN` vuoto = ogni portatore del token API è admin**
   (`backend/security.py`, `is_admin=not bool(settings.delir_admin_token)`).
   Nello stack locale è voluto: l'overlay lo svuota. In
   `docker-compose.prod.yml`, però, è vuoto di default. In produzione va
   impostato, oppure il comportamento va invertito (senza admin token, nessuno
   è admin).
2. Nella macchina di sviluppo la porta host di PostgreSQL DEV è `55300` e non
   `5432`, perché la 5432 è occupata da un altro progetto. La tabella in
   `ops/local-release.md` ora lo indica.
3. Le funzioni AI su STAGING e PROD-SIM non sono state provate:
   `OPENAI_API_KEY` è il placeholder. Serve una chiave dedicata per ambiente,
   con tetto di spesa.

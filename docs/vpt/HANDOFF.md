# Dove siamo adesso

Aggiornato: 2026-11-23, fine della sessione che ha preparato dataset e workflow.

## Punto attivo

**B1b**, branch `feat/sim-prosimos-import-ui` (impilato su `feat/sim-prosimos-import`,
PR #169). In corso dal 2026-11-23.

- Fatto: endpoint `POST /v1/workspace/bpmn-models/{id}/prosimos-import` con test API
  (import SIMOD, 400 con motivo, 404, run "così com'è" che arriva al motore).
- Da fare: nel dialogo "Importa da file" dell'editor, quando l'import locale non
  riesce (scenari SIMOD), chiamare l'endpoint, mostrare il report in linguaggio di
  business e offrire "Simula così com'è" (`simulation-model-runs` con `model`);
  e2e con mock e gate UX.

B1a (`backend/simulation/ir/from_prosimos.py`) è fatto: vedi `LOG.md`.

## Ultima misura

B1a: `uv run pytest --noconftest tests/simulation/test_prosimos_import.py` → 61/61;
19/19 scenari importati e ricompilati con gli stessi parametri, nessuna approssimazione.

## Come riprendere B1

1. Leggi [`WORKFLOW.md`](./WORKFLOW.md) e la voce più recente di [`LOG.md`](./LOG.md).
2. I 19 scenari sono i `*.json` in `datasets/extraneous-delays/inputs/synthetic` (16)
   e `inputs/real-life` (3). Oggi l'import esiste solo nel frontend e rifiuta i
   metadati SIMOD (`process_model`, `model_type`, `granule_size`): problema 6 di
   `docs/simulation-plan.md`.
3. Meta: 19/19 importati lato server senza modifiche. Il test va scritto per primo
   e deve fallire; poi si itera finché passa.
4. Il punto ha UI (l'import dal frontend): vale il gate UX.

## CI

Fino al 2026-11-23 `main` era rosso su 5 e2e del simulatore (`simulation-escalation`,
`simulation-eventlog`), rimasti indietro rispetto ai commit del 23 novembre. La PR
#168 li ha corretti: un difetto vero (log con soli completamenti senza confronto per
attività) e test con copy e mock vecchi.

## Ambiente

- Sessioni cloud sull'ambiente **BK-GPT** (consente zenodo.org e data.4tu.nl).
- I test che non toccano il database girano con `uv run pytest --noconftest ...`;
  la suite completa richiede Postgres (`cd ops && docker compose up -d`) o la CI.
- Postgres in cloud senza Docker (il daemon non c'è): `apt-get install -y
  postgresql-16-pgvector`, poi come utente `postgres` `initdb -U delir_super
  --auth=trust` in `/var/lib/postgresql/delir-test/data`, `pg_ctl ... -o '-p 5432
  -c listen_addresses=127.0.0.1' start`, `CREATE DATABASE delir`, gli script
  `ops/postgres/init/*.sh` con `POSTGRES_USER=delir_super POSTGRES_DB=delir` e le
  password di test della CI, poi `alembic upgrade head` e
  `alembic -c alembic_workspace.ini upgrade head` con le URL della CI. Con questo la
  suite `tests/simulation` gira intera (655 test il 2026-11-23).
- Playwright in cloud: il repo fissa una versione diversa da quella preinstallata.
  Usa una config locale non committata che estende `playwright.config.ts` con
  `launchOptions.executablePath: '/opt/pw-browsers/chromium'`.

## Decisioni aperte per Sohayb

- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).

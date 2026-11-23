# Dove siamo adesso

Aggiornato: 2026-11-23, fine della sessione che ha preparato dataset e workflow.

## Punto attivo

Nessuno. **B1a è fatto** sul branch `feat/sim-prosimos-import` (PR aperta, base
`claude/funny-babbage-cw4b84` finché la #168 non è mergiata). Il prossimo è
**B1b**: l'editor importa gli scenari passando da `import_prosimos` lato server,
con il report d'import in linguaggio di business e il gate UX. In alternativa
**UX-01**.

Cosa sa fare B1a (`backend/simulation/ir/from_prosimos.py`):
- scenari Prosimos e SIMOD con il loro BPMN → `SimulationModel`, più note per il consulente;
- porte d'unione, calendari non usati, attività istantanee: note informative;
- rami senza probabilità, probabilità arrotondate: note di approssimazione;
- batch, calendari FUZZY, sezioni sconosciute, organici frazionari, elementi assenti
  o del tipo sbagliato nel BPMN: import rifiutato con il motivo.

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
- Playwright in cloud: il repo fissa una versione diversa da quella preinstallata.
  Usa una config locale non committata che estende `playwright.config.ts` con
  `launchOptions.executablePath: '/opt/pw-browsers/chromium'`.

## Decisioni aperte per Sohayb

- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).

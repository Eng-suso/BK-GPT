# Dove siamo adesso

Aggiornato: 2026-11-24, dopo CONF-01, CONF-02 (conformance log ↔ BPMN) e SEC-ADMIN.

## Punto attivo

Nessuno. Il prossimo da prendere è **B1, import Prosimos tollerante**
(`feat/sim-prosimos-import`, vedi [`PLAN.md`](./PLAN.md)). In parallelo si può
prendere **UX-01** (leggibilità di "Reale contro simulato"), emerso dal gate UX.

## Ultima misura

CONF-02: e2e `simulation-eventlog` 12/12 su chromium e mobile-chrome, axe pulito;
screenshot in `docs/vpt/ux/conformance/`. CONF-01: LoanApp 500/500 casi conformi.

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

- Impostare `DELIR_ADMIN_TOKEN` in staging e prod: senza, le cancellazioni ora
  rispondono 403 (SEC-ADMIN).
- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).

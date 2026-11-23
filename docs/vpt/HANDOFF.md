# Dove siamo adesso

Aggiornato: 2026-11-23, fine della sessione che ha preparato dataset e workflow.

## Punto attivo

**B1a, import Prosimos lato server**, branch `feat/sim-prosimos-import` (partito da
`claude/funny-babbage-cw4b84`, PR #168 non ancora mergiata). In corso dal 2026-11-23.

Decisioni prese all'avvio, dai dati dei 19 scenari:
- 640 durate `fix 0` (attività istantanee, quasi tutte in AcademicCredentials):
  l'IR accetta la durata zero invece di riscriverla;
- 47 orari con microsecondi (`23:59:59.999000`): l'IR accetta fino a 6 decimali;
- 48 decisioni con un solo ramo a probabilità 1 sono porte di unione: si ricostruiscono
  dal BPMN, nessuna probabilità da importare;
- 4 calendari non usati da nessuna risorsa: il report li segnala.

Dopo B1a: **B1b** (frontend tramite il server) o **UX-01**.

## Ultima misura

D0 dataset: `scripts/fetch_datasets.py verify` → 3/3 dataset nel repo presenti;
`fetch` di BPIC 2012, BPIC 2013, BPIC 2020 → MD5 coincidente.

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

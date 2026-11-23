# Dove siamo adesso

Aggiornato: 2026-11-23, fine della sessione che ha preparato dataset e workflow.

## Punto attivo

Nessuno. Il prossimo da prendere è **B1, import Prosimos tollerante**
(`feat/sim-prosimos-import`, vedi [`PLAN.md`](./PLAN.md)).

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

## Ambiente

- Sessioni cloud sull'ambiente **BK-GPT** (consente zenodo.org e data.4tu.nl).
- I test che non toccano il database girano con `uv run pytest --noconftest ...`;
  la suite completa richiede Postgres (`cd ops && docker compose up -d`) o la CI.

## Decisioni aperte per Sohayb

- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).

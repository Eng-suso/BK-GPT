# G3b: benchmark dei motori scientifici

Punto G3b di [`docs/vpt/PLAN.md`](../../../../docs/vpt/PLAN.md), con il protocollo di
[`docs/vpt/PROTOCOL.md`](../../../../docs/vpt/PROTOCOL.md). Sui 25 log di sviluppo (holdout
chiusi) misura "B = A", SIMOD, SIMOD con ritardi estranei, ProSiT, AgentSimulator, SIMOD con
arrivi AT-KDE e l'ablazione per componente, con le sei distanze di B2, IC 95%, tempo di
discovery, tempo di simulazione e picco di memoria. Le schede di go/no-go sono in
[`docs/vpt/LOG.md`](../../../../docs/vpt/LOG.md), scritte prima della misura; i verdetti in
[`results.md`](./results.md) e `verdicts.json`.

## Rifare tutto

```bash
uv run python scripts/fetch_datasets.py fetch at-kde prosit agentsimulator simod bpic2012 bpic2013-incidents
tests/simulation/benchmark/g3b/setup_envs.sh                 # venv di ricerca in /var/tmp/delir-g3b/envs (serve Java per SIMOD)
uv run python tests/simulation/benchmark/g3b/run.py           # 25 log × 2 fasi × 9 configurazioni; riprende da dove si e' fermato
uv run python tests/simulation/benchmark/g3b/report.py        # results.md e verdicts.json
uv run python tests/simulation/benchmark/g3b/engine_check.py  # Prosimos della ricerca contro il percorso del prodotto
uv run pytest --noconftest -q tests/simulation/benchmark/g3b/test_g3b.py
```

Opzioni di `run.py`: `--logs`, `--configs`, `--phases validation test`, `--force` (rifà le
misure scritte), `--retry-failed` (riprova i falliti), `--refresh-val01` (ricalcola VAL-01
sugli scenari in cache). Più processi in parallelo vanno bene su log diversi (o fasi diverse
dello stesso log), mai sulla stessa coppia log-fase.

Tempo sulla macchina di riferimento (4 vCPU, 15 GB): circa 9 ore con 2-3 processi; quasi
tutto nei log grandi (BPIC 2017 W, BPIC 2012, BPIC 2013) e nelle configurazioni che finiscono
fuori budget, fermate al limite del §6.

## Come misura

- **Fasi.** `validation`: discovery sul fit (train meno l'ultimo 20% dei casi), previsione
  della validazione (`protocol.train_validation`). `test`: discovery sull'intero train,
  previsione del test. Tutto dentro `protocol.selection_phase()`.
- **Repliche.** 10, seed `20261124 + replica`, tanti casi quanti il periodo da prevedere, dal
  suo primo inizio. Del periodo gli strumenti sanno solo questo (AgentSimulator riceve un log
  fittizio con il numero dei casi e il primo inizio).
- **Simulatore.** Gli scenari SIMOD girano su Prosimos 2.1.0 chiamato direttamente
  (`tools/prosimos_sim.py`), perché il runner del prodotto non accetta arrivi dati (AT-KDE,
  arrivi rigiocati) né l'ablazione dei calendari. `engine_check.py` mostra che, a parità di
  scenario e seed, le repliche sono identiche a quelle del percorso del prodotto di G3.
- **Costo.** Tempo reale e somma della memoria residente dell'albero dei processi, campionata
  ogni 0,2 s. Budget del §6 fatto rispettare: discovery 2 h e 12 GB, replica 10 minuti; oltre,
  `out_of_budget` con tempo e memoria misurati, sconfitta su tutte le metriche.
- **Esiti degli strumenti.** Codice d'uscita 3 = non applicabile (AT-KDE con meno di 14
  giorni di arrivi; AgentSimulator con un input di un solo giorno), 4 = fuori budget. Non
  applicabile e fallito contano come sconfitta, per il candidato e per la base.
- **Ripetibilità.** Con lo stesso seed "B = A", gli scenari SIMOD simulati, AT-KDE e
  AgentSimulator danno metriche identiche al bit. ProSiT no: i parametri del control flow
  seguono l'ordine in cui Python itera le transizioni della rete di Petri; fra due passate su
  Loan_Application le medie cambiano dentro gli IC. La discovery di SIMOD non ha seed (G3):
  gli scenari scoperti restano in cache in `/var/tmp/delir-g3b/work`, non nel repo.

## Cosa c'è

| Percorso | Cosa |
| --- | --- |
| `run.py` | driver: log, fasi, configurazioni, misura, risultati |
| `report.py` | tabelle e verdetti delle schede (PROTOCOL.md §7) |
| `engine_check.py`, `engine_check.json` | diagnosi: simulatore della ricerca = percorso del prodotto |
| `configs/simod_{diff,extr}.yml` | configurazioni di G3 (benchmark di SIMOD) senza log di test |
| `tools/` | script che girano nei venv di ricerca e non importano nulla di DeliR |
| `setup_envs.sh` | crea i venv di ricerca |
| `results/<log>/<fase>/<config>.json` | un risultato per file: metriche per replica, identificabilità, costo, VAL-01 |

## Licenze

Il codice esterno (SIMOD e AT-KDE Apache 2.0, ProSiT e AgentSimulator MIT, come da
`datasets/manifest.json`) resta nella cache di `fetch_datasets` e nei venv di ricerca: nessun
modulo del prodotto lo importa (LIC-01 deciderà cosa può entrare). Nel repo ci sono solo le
metriche; i log 4TU (BPIC 2012, BPIC 2013) non entrano.

# DeliR Verified Process Twin — piano operativo

Questo file è il punto di partenza di ogni sessione che lavora sul VPT. La
strategia (tesi, ipotesi, architettura, letteratura) sta nel doc
[DeliR Verified Process Twin — Product & Research Master Plan V2](https://claude.ai/artifact/YDeL5nCYLmkDet5UwPjfbU);
qui ci sono i blocchi da eseguire, la meta di ognuno e come si misura. Lo stato
delle voci SIM è in [`../simulation-plan.md`](../simulation-plan.md), i dataset in
[`../../datasets/README.md`](../../datasets/README.md).

## Come si lavora

1. **Prima di iniziare:** leggi questo file e le ultime tre voci di
   [`LOG.md`](./LOG.md). Controlla i branch aperti rispetto a `main`, rivedi
   quello che c'è e mergialo se è pronto.
2. **Prendi un blocco** con stato `da fare` e dipendenze chiuse. Mettilo `in corso`
   con la data, in un commit sul suo branch.
3. **Itera fino alla meta.** Ogni blocco ha una meta numerica e un comando che la
   misura. Dopo ogni tentativo lancia la misura e scrivi il numero in `LOG.md`.
   Se la meta non è raggiunta: diagnosi, correzione, nuova misura. Il blocco non si
   chiude finché la misura non raggiunge la meta.
4. **La meta non si abbassa per chiudere.** Cambiarla richiede una decisione di
   Sohayb, scritta in `LOG.md` con data e motivo. Le mete marcate *proposta* vanno
   confermate da Sohayb alla prima sessione che le usa.
5. **Bloccato?** Scrivi in `LOG.md` cosa blocca e chi lo sblocca, metti il blocco
   `bloccato` e passa a un altro.
6. **Chiusura:** test verdi, PR, merge su `main`, push. Aggiorna la tabella qui
   sotto, `simulation-plan.md` se cambia una voce SIM, e aggiungi in cima a
   `LOG.md` la voce di chiusura. Poi la sessione si chiude, così il prossimo
   riparte pulito.
7. **Commit:** piccoli e frequenti, a nome di Sohayb Raqaq, senza trailer di
   coautore.

Binari: **Prod** = serve per vendere in sicurezza; **Ric** = ricerca, vantaggio
tecnologico; **PV** = validazione con i clienti. Un risultato di ricerca non
diventa automaticamente una funzione di prodotto.

## Blocchi

Stato: `da fare` · `in corso` · `bloccato` · `fatto`.

### V0 — Fondamenta

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B0 parità del motore | `fix/sim-engine-parity` | Prod | Nessun run `completed` senza KPI; runner con token, limiti, scadenza | test del runner e della coda in CI | — | fatto (2026-11-23) |
| D0 dataset nel repo | `claude/funny-babbage-cw4b84` | Prod | Tutti i dataset nel manifest; ogni dataset scaricabile verifica l'MD5 | `uv run python scripts/fetch_datasets.py verify` e `fetch --all` | — | fatto (2026-11-23) |
| B1 import Prosimos tollerante | `feat/sim-prosimos-import` | Prod | 19/19 scenari di `datasets/extraneous-delays/inputs` importati lato server senza modifiche, metadati SIMOD compresi | test che importa ogni `*.json` dei 19 scenari | — | da fare |
| Track B isolamento tenant | vedi `docs/deployment-and-tenancy.md` | Prod | Test cross-tenant su API, worker, memoria e checkpoint verdi | suite cross-tenant | blocker VM e dominio (Sohayb) | bloccato |

### V1 — Misura

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B2 harness di valutazione | `feat/sim-eval-harness` | Ric | Per i 19 scenari: run replicati sugli scenari del paper, W1 del cycle time, NGD, RED/CED/CAR salvati in `baseline.json`; stesso seed → risultati identici; scarto dalle metriche di `paper-results` entro il 10% (*proposta*) | `uv run python tests/simulation/benchmark/run_baseline.py` + confronto con `datasets/extraneous-delays/paper-results` | B1 | da fare |
| SIM-36 baseline pubblica | `feat/sim-benchmark-baseline` | Ric | Baseline "B = A" misurata su BPIC 2012 e BPIC 2013 e salvata | `run_baseline.py bpic2012`, `run_baseline.py bpic2013_incidents` | D0 | da fare |
| VPT-10 regimi stazionari | `feat/sim-steady-state` | Ric | Ogni riga del benchmark riporta il regime di A e di B; errore riportato anche solo sulle coppie nello stesso regime | campo `regime` in `baseline.json` | B2 | da fare |

### V2 — Twin dai dati

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| G3 spike SIMOD | `spike/sim-simod-discovery` | Ric | SIMOD scopre i 3 log reali dal train, valutati sul test; lo scenario prodotto si importa in DeliR; decisione G3 scritta in `LOG.md` | harness B2 sugli scenari SIMOD | B1, B2 | da fare |
| B3 discovery dei parametri (SIM-16) | `feat/sim-discovery-core` | Ric → Prod | Sui sintetici: probabilità dei gateway entro ±0,05 e media delle durate entro ±10% della verità (*proposta*); sui reali il twin batte "B = A" su ≥ 3 log con IC 95% (H1) | harness B2 | G3 | da fare |
| VPT-08 traccia di derivazione | `feat/sim-derivation-trace` | Prod | 100% dei parametri non Manual risale al passaggio esatto della fonte o all'osservazione | test sul contratto dei candidati | B3 | da fare |
| B4 checklist del twin (SIM-18) | `feat/sim-discovery-ui` | Prod | E2E: un log porta a un twin validato senza toccare JSON | Playwright | B3 | da fare |
| B5 ritardi estranei | `feat/sim-extraneous-delays` | Ric | Sui sintetici con 1, 3, 5 timer, distanza pari o migliore di quella del paper in `paper-results` | harness B2 | B3 | da fare |
| VPT-07 spike object-centric | `spike/sim-ocel` | Ric | Su ≥ 2 log OCEL pubblici misurata la perdita da appiattimento; decisione scritta | script dello spike | B2 | da fare |

### V3 — Incertezza

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| VPT-01/02 belief e simulazione a due livelli | `feat/sim-parameter-belief` | Ric | Copertura empirica degli IC 90% fra 80% e 95% su held-out (H3) | harness B2, coppie A → B | B3 | da fare |
| VPT-03 prior dalle interviste | `feat/sim-claim-priors` | Ric | Con log troncati al 25%, errore minore del solo log (H2) | harness B2 su log troncati | VPT-01 | da fare |

### V4 — Active Discovery

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| VPT-04/05 domande per valore dell'informazione | `feat/sim-active-discovery` | Ric → Prod | Riduzione della varianza del Δ KPI per domanda migliore dell'ordine euristico (H4) | esperimento simulato con fonti a affidabilità diversa | VPT-01, B2 | da fare |

### V5 — Decisione

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B6 throughput (G2) | `spike/sim-throughput` | Prod | Misurati i run al minuto; what-if < 60 s (10 repliche × 1.000 casi) | script di carico | B0 | da fare |
| B7 ottimizzazione (SIM-26) | `feat/sim-optimization` | Prod | Frontiera di Pareto; raccomandazione finale sempre ri-simulata con IC | test + harness | B6, V3 | da fare |
| VPT-09 attività svolte da agenti AI | `feat/sim-agent-tasks` | Prod | What-if "automatizziamo con un agente" con IC che include l'incertezza sull'agente | test | VPT-01 | da fare |

### V6 — Ciclo chiuso

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B8 drift e ricalibrazione (SIM-29) | `feat/sim-recalibration` | Prod | Un twin con drift rilevato perde lo stato "validato" e propone la ricalibrazione | test su log con cambio di regime | VPT-10, B3 | da fare |
| VPT-06 track record | `feat/sim-track-record` | Prod | Errore previsto contro osservato registrato per ogni twin | test | SIM-28 | da fare |

### Trasversale

| Blocco | Binario | Meta | Stato |
| --- | --- | --- | --- |
| PV-01…04 | PV | 10 interviste a consulenti; formato pilot; willingness to pay; tempo al primo insight misurato | da fare (Sohayb) |

## Ordine consigliato

B1 → B2 → SIM-36 e G3 in parallelo → B3. Finché B2 non ha una baseline misurata,
nessuna affermazione di fedeltà entra in materiali commerciali.

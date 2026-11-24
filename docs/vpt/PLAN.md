# DeliR Verified Process Twin — piano operativo

Questo file è il punto di partenza di ogni sessione che lavora sul VPT. La
strategia (tesi, ipotesi, architettura, letteratura) sta nel doc
[DeliR Verified Process Twin — Product & Research Master Plan V2](https://claude.ai/artifact/YDeL5nCYLmkDet5UwPjfbU);
qui ci sono i blocchi da eseguire, la meta di ognuno e come si misura. Lo stato
delle voci SIM è in [`../simulation-plan.md`](../simulation-plan.md), i dataset in
[`../../datasets/README.md`](../../datasets/README.md).

## Come si lavora

Le regole complete sono in [`WORKFLOW.md`](./WORKFLOW.md). In breve:

1. leggi [`HANDOFF.md`](./HANDOFF.md), questo file e le ultime voci di [`LOG.md`](./LOG.md);
2. prendi un punto `da fare` con dipendenze chiuse e mettilo `in corso`;
3. itera finché il comando di misura raggiunge la meta, aggiornando `HANDOFF.md` a ogni misura;
4. test, e gate UX con screenshot se il punto tocca ciò che il cliente vede;
5. PR con commit piccoli, CI verde, merge su `main`, branch allineato;
6. punto `fatto`, `HANDOFF.md` riscritto, voce in `LOG.md`, sessione chiusa.

La meta non si abbassa per chiudere. Le mete marcate *proposta* vanno confermate da
Sohayb. Regola di prodotto: DeliR mangia la complessità del cliente.

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
| B1a import Prosimos lato server | `feat/sim-prosimos-import` | Prod | 19/19 scenari di `datasets/extraneous-delays/inputs` importati nell'IR, metadati SIMOD compresi; ricompilati, ritrovano gli stessi parametri (durate per risorsa, probabilità, arrivi, calendari, organici, costi, attese); ogni differenza dichiarata nel report d'import | `uv run pytest --noconftest tests/simulation/test_prosimos_import.py` | — | fatto (2026-11-24) |
| B1b import dal frontend tramite il server | `feat/sim-prosimos-import-ui` | Prod | Uno scenario che l'editor non sa rappresentare (oggi tutti quelli SIMOD) si importa dal server e si simula così com'è; il report d'import si legge in linguaggio di business; gate UX | `tests/simulation/test_prosimos_import_api.py` + e2e + gate UX | B1a | fatto (2026-11-24) |
| SEC-ADMIN admin implicito | `ccr-9b6e10c9-jmjsbm` | Prod | Fuori da dev/local/test, senza `DELIR_ADMIN_TOKEN` nessun client è amministratore e le cancellazioni rispondono 403 | `tests/server/test_app.py` | — | fatto (2026-11-24) |
| CAL-01 calendari probabilistici (FUZZY) di SIMOD | `feat/sim-fuzzy-calendars` | Prod | Uno scenario SIMOD con calendari FUZZY si importa senza perdere la disponibilità probabilistica delle risorse, si ricompila identico e gira sul runner Prosimos 2.1; nessun rifiuto per FUZZY | test di import e round trip su uno scenario FUZZY scoperto da SIMOD sul dataset + run sul runner | B1a | fatto (2026-11-24) |
| Track B isolamento tenant | vedi `docs/deployment-and-tenancy.md` | Prod | Test cross-tenant su API, worker, memoria e checkpoint verdi | suite cross-tenant | blocker VM e dominio (Sohayb) | bloccato |

### UX — Leggibilità (regola: mangiare la complessità)

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| UX-01 reale contro simulato leggibile | `fix/ux-real-vs-simulated` | Prod | Nel percorso ordinario nessun termine tecnico (IC 95%, P50/P90, 2-grammi, warm-up, errore assoluto medio, "repliche" al plurale con 1): ognuno diventa una frase o va nei dettagli per specialisti; plurali corretti; su mobile il pannello si legge senza scorrere oltre il canvas; gate UX superato | screenshot in `docs/vpt/ux/complete-only-log/` come "prima", nuovi screenshot desktop e mobile, prova del consulente | — | fatto (2026-11-24, #173) |

### V1 — Misura

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B2 harness di valutazione | `feat/sim-eval-harness` | Ric | (1) Riproducibile: con lo stesso seed i 19 scenari danno lo stesso `baseline.json`, bit per bit. (2) Allineato al paper sui 3 log reali (AcademicCredentials, BPIC 2012 W, BPIC 2017 W): lo scenario SIMOD simulato così com'è sullo stack reale (import, database, coda, runner Prosimos 2.1) e confrontato con il log di test, con lo stesso numero di repliche del paper; per RED, AED e W1 del cycle time la differenza fra la nostra media e la riga `original` di `paper-results` è minore della somma dei due intervalli di confidenza. Ogni metrica fuori resta aperta finché la causa non è trovata e corretta o spiegata con una prova in `LOG.md`. (3) Baseline sui 16 sintetici: W1, NGD, RED, AED, CED, CAR con i loro intervalli, riferimento per B3 e B5 | il comando dell'harness, consegna di B2, su `scripts/vpt_stack.sh`; metriche calcolate come `log-distance-measures` 2.2 (la libreria del paper), confrontate con `datasets/extraneous-delays/paper-results` | B1 | fatto (2026-11-24): riproducibile bit per bit, 9/9 metriche dentro sui 3 reali, baseline dei 16 sintetici in `tests/simulation/benchmark/b2/` |
| SIM-36 baseline pubblica | `feat/sim-benchmark-baseline` | Ric | Baseline "B = A" misurata su BPIC 2012 e BPIC 2013 e salvata | `run_baseline.py bpic2012`, `run_baseline.py bpic2013_incidents` | D0 | fatto (2026-11-24, #178): metriche di B2 con IC 95% in `tests/simulation/benchmark/sim36/` |
| VPT-10 regimi stazionari | `feat/sim-steady-state` | Ric | Ogni riga del benchmark riporta il regime di A e di B; errore riportato anche solo sulle coppie nello stesso regime | campo `regime` in `baseline.json` | B2 | da fare |

### V2 — Twin dai dati

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| G3 spike SIMOD | `spike/sim-simod-discovery` | Ric | SIMOD scopre i 3 log reali dal train, valutati sul test; lo scenario prodotto si importa in DeliR; decisione G3 scritta in `LOG.md` | harness B2 sugli scenari SIMOD | B1, B2 | da fare |
| B3 discovery dei parametri (SIM-16) | `feat/sim-discovery-core` | Ric → Prod | Sui sintetici: probabilità dei gateway entro ±0,05 e media delle durate entro ±10% della verità (*proposta*); sui reali il twin batte "B = A" su ≥ 3 log con IC 95% (H1) | harness B2 | G3 | da fare |
| VPT-08 traccia di derivazione | `feat/sim-derivation-trace` | Prod | 100% dei parametri non Manual risale al passaggio esatto della fonte o all'osservazione | test sul contratto dei candidati | B3 | da fare |
| B4 checklist del twin (SIM-18) | `feat/sim-discovery-ui` | Prod | E2E: un log porta a un twin validato senza toccare JSON; gate UX superato con la prova del consulente | Playwright | B3 | da fare |
| B5 ritardi estranei | `feat/sim-extraneous-delays` | Ric | Sui sintetici con 1, 3, 5 timer, distanza pari o migliore di quella del paper in `paper-results` | harness B2 | B3 | da fare |
| VPT-07 spike object-centric | `spike/sim-ocel` | Ric | Su ≥ 2 log OCEL pubblici misurata la perdita da appiattimento; decisione scritta | script dello spike | B2 | da fare |

### Conformance delle esecuzioni (emersa dall'audit del 2026-11-23)

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| CONF-01 token replay log ↔ BPMN | `ccr-9b6e10c9-jmjsbm` | Prod | Fitness per log e per variante, casi conformi, elementi eseguiti fuori ordine e rimasti in attesa; log simulato dal modello → fitness 1 | `tests/eventlog/test_conformance.py` (LoanApp: 500/500 conformi; 3 perizie tolte → 3 deviazioni trovate) | — | fatto (backend + API) |
| CONF-02 vista di conformance | `ccr-9b6e10c9-jmjsbm` | Prod | Il consulente vede fitness, casi fuori processo e deviazioni sul BPMN senza leggere JSON; gate UX superato | `e2e/simulation-eventlog.spec.ts` (desktop e mobile, axe) + screenshot in `docs/vpt/ux/conformance/` | CONF-01 | fatto (2026-11-24) |
| CONF-03 allineamenti ottimi | da aprire | Ric | Per ogni caso non conforme la sequenza minima di correzioni (A*), confrontata con il replay | test su log con deviazioni note | CONF-01 | da fare |

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
| B6 throughput (G2) | `spike/sim-throughput` | Prod | Misurati i run al minuto; what-if < 60 s (10 repliche × 1.000 casi) | script di carico | B0 | fatto |
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

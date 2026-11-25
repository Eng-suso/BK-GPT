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
| IMP-01 avviso sugli arrivi troncati | `feat/sim-import-expon-warning` | Prod | Importando uno scenario con arrivi `expon` la cui media è vicina al massimo (Prosimos 2.1 li tronca: arrivi più fitti e code più lunghe del log), DeliR avvisa il consulente in linguaggio di business, con cosa cambia e cosa fare; lo scenario resta com'era. Avvisano le 4 varianti di Procure_to_Pay, nessuno dei 15 altri scenari di `datasets/extraneous-delays/inputs`; gate UX | test di import sui 19 scenari + e2e + gate UX | B1a | fatto (2026-11-24, #185): 4/4 Procure_to_Pay avvisano, 0/15 altri; e2e 4/4, screenshot in `docs/vpt/ux/imp-01/` |
| Track B isolamento tenant | vedi `docs/deployment-and-tenancy.md` | Prod | Test cross-tenant su API, worker, memoria e checkpoint verdi | suite cross-tenant | VM e dominio: Sohayb li sblocca (deciso il 2026-11-24) | bloccato |

### UX — Leggibilità (regola: mangiare la complessità)

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| UX-01 reale contro simulato leggibile | `fix/ux-real-vs-simulated` | Prod | Nel percorso ordinario nessun termine tecnico (IC 95%, P50/P90, 2-grammi, warm-up, errore assoluto medio, "repliche" al plurale con 1): ognuno diventa una frase o va nei dettagli per specialisti; plurali corretti; su mobile il pannello si legge senza scorrere oltre il canvas; gate UX superato | screenshot in `docs/vpt/ux/complete-only-log/` come "prima", nuovi screenshot desktop e mobile, prova del consulente | — | fatto (2026-11-24, #173) |

### V1 — Misura

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| B2 harness di valutazione | `feat/sim-eval-harness` | Ric | (1) Riproducibile: con lo stesso seed i 19 scenari danno lo stesso `baseline.json`, bit per bit. (2) Allineato al paper sui 3 log reali (AcademicCredentials, BPIC 2012 W, BPIC 2017 W): lo scenario SIMOD simulato così com'è sullo stack reale (import, database, coda, runner Prosimos 2.1) e confrontato con il log di test, con lo stesso numero di repliche del paper; per RED, AED e W1 del cycle time la differenza fra la nostra media e la riga `original` di `paper-results` è minore della somma dei due intervalli di confidenza. Ogni metrica fuori resta aperta finché la causa non è trovata e corretta o spiegata con una prova in `LOG.md`. (3) Baseline sui 16 sintetici: W1, NGD, RED, AED, CED, CAR con i loro intervalli, riferimento per B3 e B5 | il comando dell'harness, consegna di B2, su `scripts/vpt_stack.sh`; metriche calcolate come `log-distance-measures` 2.2 (la libreria del paper), confrontate con `datasets/extraneous-delays/paper-results` | B1 | fatto (2026-11-24): riproducibile bit per bit, 9/9 metriche dentro sui 3 reali, baseline dei 16 sintetici in `tests/simulation/benchmark/b2/` |
| SIM-36 baseline pubblica | `feat/sim-benchmark-baseline` | Ric | Baseline "B = A" misurata su BPIC 2012 e BPIC 2013 e salvata | `run_baseline.py bpic2012`, `run_baseline.py bpic2013_incidents` | D0 | fatto (2026-11-24, #178): metriche di B2 con IC 95% in `tests/simulation/benchmark/sim36/` |
| SIM-36b baseline sui log train/test | `feat/sim-benchmark-train-test` | Ric | "B = A" (impara dal train, prevede il test) misurata sui 3 log reali del paper (AcademicCredentials, BPIC 2012 W, BPIC 2017 W) con le metriche, le repliche e il formato di B2, salvata nel repo con il comando per rifarla; BPIC 2013 incidents marcato nel benchmark come non adatto al confronto A→B (è una foto degli incidenti aperti: con ogni taglio B è troncato al 100%) | `run_baseline.py` sui 3 log train/test | SIM-36 | fatto (2026-11-24): W1 28,8 / 28,1 / 30,6 h; contro SIMOD di B2 "B = A" vince 17/18 confronti; `tests/simulation/benchmark/sim36/` |
| VPT-10 regimi stazionari | `feat/sim-steady-state` | Ric | Ogni riga del benchmark riporta il regime di A e di B; errore riportato anche solo sulle coppie nello stesso regime | campo `regime` in `baseline.json` | B2 | da fare |

### P0 — Programma di ricerca (Master Plan V2, decisione di Sohayb del 2026-11-24)

Prima protocollo, audit e G3b; nessun candidato si implementa prima. Ogni punto qui sotto
ha criteri quantitativi, test riproducibili, dipendenze e condizioni di go/no-go scritti
prima della misura. Le mete marcate *proposta* vanno confermate da Sohayb.

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| LIC-01 audit delle licenze (P0) | `chore/license-audit` | Prod | Inventario di ogni componente di simulazione e discovery con versione e commit effettivamente in uso (Prosimos 2.1.0 nel runner, SIMOD, pm4py, …) e di tutte le dipendenze transitive dei venv del runner, del backend e della discovery; per ognuna licenza, compatibilità con un prodotto commerciale chiuso e strada (sostituzione, autorizzazione, implementazione indipendente); richiesta scritta ai titolari di Prosimos inviata (*proposta*) | report generato da uno script ripetibile, rivisto da Sohayb | — | da fare |
| PROTO-01 protocollo sperimentale (P0) | `docs/vpt-protocol` | Ric | `docs/vpt/PROTOCOL.md`: log divisi in osservabilità completa, parziale e sintetici con verità nota; per ogni log e metrica, identificabile oppure NOT VALIDATED con il motivo; nessun log escluso (BPIC 2013 resta, con le metriche non identificabili dichiarate); log holdout indipendenti scelti e congelati per hash prima di G3b; divisione train / validazione / test; budget di calcolo; modello di go/no-go per componente (*proposta*) | il documento + un test che fallisce se il codice di selezione legge un log holdout | — | da fare |
| G3b benchmark dei motori scientifici (P0) | `spike/sim-g3b-ablation` | Ric | Sui log del protocollo, holdout esclusi: "B = A", SIMOD, SIMOD con ritardi estranei, ProSiT, AgentSimulator, SIMOD con arrivi AT-KDE e ablazione per componente; metriche di B2 con IC 95% più tempo di discovery, tempo di simulazione e picco di memoria; codice esterno solo nell'ambiente di ricerca, mai nel prodotto finché LIC-01 non lo ammette (*proposta*) | harness B2 | PROTO-01 | da fare |
| VAL-01 validazione formale all'import (P0) | `feat/sim-formal-validation` | Prod | All'import nessun deadlock né livelock, terminazione raggiungibile da ogni stato, probabilità di uscita da ogni ciclo maggiore di zero e numero atteso di ripetizioni finito; lo scenario SIMOD di AcademicCredentials con il ciclo a uscita 0 (G3) è rifiutato; i 19 scenari di `datasets/extraneous-delays/inputs` e gli scenari SIMOD validi di G3 passano; il messaggio dice in linguaggio di business cosa non torna; gate UX (*proposta*) | test sull'IR + e2e + gate UX | — | da fare |
| ENG-01 Simulation Engine Interface (P0) | `feat/sim-engine-interface` | Prod | Fra l'IR e il motore una sola interfaccia (valida, compila, esegue, annulla, risultati); Prosimos è un adattatore e nessun modulo fuori dall'adattatore lo importa (regola ast-grep bloccante); canvas, agenti, API pubbliche e modelli invariati: suite `tests/simulation` ed e2e verdi senza modificarli (*proposta*) | regola ast-grep + suite | — | in corso (dal 2026-11-25) |
| ENG-02 motore di esecuzione proprietario, se necessario (P1) | `feat/sim-native-engine` | Prod | Go/no-go scritto dopo LIC-01 (autorizzazione per Prosimos, alternativa permissiva o motore proprio); se go: motore nativo sull'IR, dietro ENG-01, con le metriche di B2 entro gli IC di Prosimos sui 19 scenari (*proposta*) | harness B2 sui due motori | LIC-01, ENG-01 | da fare |
| PERF-01 benchmark computazionale (P1) | `spike/sim-perf-benchmark` | Ric | Per ogni configurazione di G3b: tempo di discovery, tempo di simulazione, picco di memoria e scalabilità (1.000, 10.000, 100.000 casi), riportati accanto alla fedeltà (*proposta*) | script di misura | G3b | da fare |
| CF-01 validazione controfattuale (P3) | `spike/sim-counterfactual` | Ric | Su sintetici con verità nota e interventi noti (risorse ±30%, arrivi +20%, un'attività tolta), l'IC 95% della variazione prevista dei KPI contiene quella vera in almeno il 90% dei casi (*proposta*) | harness B2 sui sintetici con interventi | PROTO-01, B3 | da fare |

### V2 — Twin dai dati

| Blocco | Branch | Binario | Meta | Misura | Dipende da | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| G3 spike SIMOD | `spike/sim-simod-discovery` | Ric | SIMOD scopre i 3 log reali dal train, valutati sul test; lo scenario prodotto si importa in DeliR; decisione G3 scritta in `LOG.md` | harness B2 sugli scenari SIMOD | B1, B2 | fatto (2026-11-24): SIMOD sì a condizioni, vedi `LOG.md` |
| B3 discovery dei parametri (SIM-16) | `feat/sim-discovery-core` | Ric → Prod | Sui sintetici: probabilità dei gateway entro ±0,05 e media delle durate entro ±10% della verità; sui 3 log reali train/test il twin scoperto dal train batte "B = A" di SIM-36b su W1 del cycle time, RED e AED, con intervalli al 95% che non si sovrappongono (H1) | harness B2 + baseline SIM-36b | G3b, B3.1-B3.3 | da fare |
| B3.1 arrivi non stazionari (P1) | `feat/sim-discovery-arrivals` | Ric → Prod | Il componente degli arrivi scelto in G3b batte gli arrivi di SIMOD su CAR e AED, prima sulla validazione e poi sul test, con IC 95% separati; go/no-go scritto prima (*proposta*) | harness B2 | G3b | da fare |
| B3.2 discovery delle attese (P1) | `feat/sim-discovery-waiting` | Ric → Prod | Le attese si attribuiscono alla causa (indisponibilità, congestione, sospensioni, batching, ritardi esterni); sui sintetici con verità nota la causa giusta in almeno il 90% delle attese; sui reali batte SIMOD con ritardi estranei su W1 e RED (*proposta*) | harness B2 | G3b | da fare |
| B3.3 control flow sound (P1) | `feat/sim-discovery-control-flow` | Ric → Prod | Ogni modello scoperto supera VAL-01; fedeltà sui percorsi (NGD) pari o migliore di SIMOD sui log del protocollo (*proposta*) | harness B2 + VAL-01 | G3b, VAL-01 | da fare |
| B3.4 risorse sensibili al contesto (P2) | `feat/sim-discovery-resources` | Ric → Prod | Assegnazione e durate dipendenti dal contesto battono le risorse di SIMOD su W1 e RED dove G3b mostra che le risorse contano (*proposta*) | harness B2 | B3.1-B3.3 | da fare |
| SEL-01 Automatic Model Selection (P2) | `feat/sim-model-selection` | Ric | Per ogni processo la configurazione si sceglie da sola sulla validazione; sui log holdout la scelta sta nell'IC della migliore configurazione a posteriori in almeno l'80% dei log (*proposta*) | harness B2 sui log holdout | B3 | da fare |
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

B1 → B2 → SIM-36 → SIM-36b e G3 → **P0: LIC-01, PROTO-01, VAL-01, ENG-01 in parallelo → G3b** →
B3.1-B3.3 → B3.4 e SEL-01 → VPT-01/02 → B8 e VPT-10 → CF-01. ENG-02 dopo LIC-01 ed ENG-01;
PERF-01 dopo G3b. Non si apre un filone nuovo finché quelli aperti non chiudono. Finché B2 non ha una baseline misurata,
nessuna affermazione di fedeltà entra in materiali commerciali.

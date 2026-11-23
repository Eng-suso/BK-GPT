# DeliR Simulation — piano di prodotto e stato

Piano originale: 4 ottobre 2026 (artifact "Piano Simulatore DeliR", non più
raggiungibile; testo recuperato da Sohayb il 23 novembre 2026). Stato verificato
sul codice di `main` il 23 novembre 2026. Questo file sostituisce l'artifact come
punto di partenza per ogni agente che lavora sul simulatore.

Documenti collegati: [roadmap P0–P2](./delir-simulation-product-roadmap.md),
[perimetro funzionale e digital twin](./design/simulation-workspace-ux.md),
[spike Prosimos 2.x](./simulation-prosimos-2x-spike.md),
[validazione](./simulation-validation.md), [benchmark](./simulation-benchmark.md).

## Tesi

La feature parity è il requisito minimo. Il vantaggio è la stessa potenza, più
semplice da configurare, capire e trasformare in una decisione difendibile.

Tre impegni:

1. ogni numero dice da dove viene;
2. ogni confronto dice quanto è certo;
3. ogni raccomandazione è stata simulata davvero, mai solo stimata.

Ciclo da chiudere: scoprire la realtà → AS-IS → calibrare il digital twin →
validarlo contro i dati → TO-BE → simulare → ottimizzare → confrontare →
decidere → implementare → osservare di nuovo.

## Architettura target

Tutte le fonti (event log, interviste, documenti, grafo dei Claim) producono
**candidati di parametro** con lo stesso contratto (Observed, Inferred, Declared,
Estimated, Manual). Il consulente approva. Il **Simulation IR** versionato è
l'unica verità che arriva al motore (Prosimos 2.1.0 dietro il runner DeliR).
L'output è sempre un event log, analizzato dallo stesso strato del process mining
reale. Validazione, ottimizzatore (frontiera di Pareto) e decision record stanno a
valle.

## Stato per voce (verificato il 2026-11-23)

Legenda: ✅ fatto · 🟡 parziale · ❌ assente.

### M0 — fondamenta affidabili

| ID | Voce | Stato | Nota |
| --- | --- | --- | --- |
| SIM-00 | Simulation IR e contract test | ✅ | `backend/simulation/ir/`, run sull'IR (SIM-37), parità TS/Python su `draft_request_cases.json` |
| SIM-05 | Report di compatibilità BPMN | ✅ | `compatibility.py`, timer senza durata dichiarati |
| SIM-06 | Log sintetico esportabile | ✅ | CSV/XES con hash, seed, revisione scenario |
| SIM-07 | Provenienza a cinque livelli | ✅ | `provenance.py`, Claim collegati (SIM-17) |

### M1 — parity del modello

| ID | Voce | Stato | Nota |
| --- | --- | --- | --- |
| SIM-01 | Distribuzioni tipizzate | 🟡 | fissa, esp., uniforme, normale, lognormale, gamma. Triangolare, Weibull, Beta assenti: pix-framework non le ha |
| SIM-02 | Calendari | ✅ | per risorsa e per arrivi, turni |
| SIM-08 | Domanda non stazionaria | ✅ | fasce orarie, ritmo per mese (runner) |
| SIM-09 | Risorse realistiche | ✅ | sistemi, ruoli, assegnazioni multiple |
| SIM-10 | Costi completi | ✅ | costi fissi per attività e per caso |
| SIM-11 | Semantica BPMN | ✅ | sottoprocessi srotolati, escalation, timer, multi-istanza |
| SIM-12 | Discipline di coda | 🟡 | priorità per attributo sì; LIFO no (Prosimos non lo ha) |
| SIM-13 | SLA come oggetto | ✅ | per segmento, nei risultati |

### M2 — esperimento rigoroso

| ID | Voce | Stato | Nota |
| --- | --- | --- | --- |
| SIM-03 | Orizzonte e warm-up | ✅ | `horizon.py`, warm-up a casi |
| SIM-04 | Seed, repliche, intervalli | ✅ | intervalli t, probabilità di miglioramento; CRN solo approssimate (RNG globale di Prosimos) |
| SIM-14 | Scenario Workspace | ✅ | AS-IS e alternative come patch, revisioni |

### M3 — digital twin dai dati (il buco strategico)

| ID | Voce | Stato | Nota |
| --- | --- | --- | --- |
| SIM-15 | Import event log | 🟡 | CSV/XES, mapping guidato, qualità. Niente estrazioni SAP |
| SIM-16 | **Discovery dei parametri** | ❌ | nessun fitting da log: arrivi, durate, gateway, risorse, calendari, ritardi |
| SIM-17 | Fusione fonti con conflitti | ✅ | disaccordi fra fonti visibili |
| SIM-18 | Checklist e readiness | 🟡 | readiness per parametro; la checklist del digital twin dipende da SIM-16 |
| SIM-19 | Validazione contro la realtà | 🟡 | report reale/simulato aggregato (W1, NGD, IC). Mancano RED/CED/CAR, held-out e benchmark |
| SIM-36 | Benchmark di fedeltà | 🟡 | metriche pronte, baseline mai misurata (4TU bloccato). Usare il dataset eval locale, sotto |

### M4 — semplice da capire

| ID | Voce | Stato |
| --- | --- | --- |
| SIM-20 | Overlay BPMN e inspector | ✅ |
| SIM-21 | Consultant / Operations View | ✅ |
| SIM-22 | Esperimenti suggeriti oltre +1 risorsa | ✅ |
| SIM-23 | What-if in linguaggio naturale | ✅ |
| SIM-24 | Interpretazione calcolata, poi scritta | ✅ |

### M5 — motore decisionale

| ID | Voce | Stato | Nota |
| --- | --- | --- | --- |
| SIM-25 | Sensitività | ✅ | ±delta con seed comune. Value of information verso la discovery: da verificare |
| SIM-26 | **Optimization Mode** | ❌ | nessuna ricerca, nessuna frontiera di Pareto |
| SIM-27 | Decision record | ✅ | export per il cliente |

### M6 — ciclo chiuso

| ID | Voce | Stato |
| --- | --- | --- |
| SIM-28 | Previsto contro reale | ✅ |
| SIM-29 | **Ricalibrazione continua e drift** | ❌ |

Voci aggiunte dopo il piano: SIM-30 capacità nel tempo, SIM-31 attributi ed esiti,
SIM-32 durate condizionali, SIM-33 parametri per fascia oraria, SIM-34 routing
condizionale (`branch_rules`), SIM-35 semantica BPMN estesa, SIM-36 benchmark,
SIM-37 contratto di run sull'IR.

## Gate

| Gate | Domanda | Esito |
| --- | --- | --- |
| G1 | Prosimos regge code, priorità, calendari? | Chiuso: Prosimos 2.1.0 nel runner DeliR |
| G2 | Quante simulazioni al minuto? | Aperto. Coda su Postgres e runner gunicorn; serve misura prima di SIM-26 |
| G3 | Discovery: `/api/discovery`, SIMOD o fitting nostro? | Aperto. Si decide con il dataset eval, sotto |
| G4 | Dove serve un LLM? | Chiuso: solo frase → patch e redazione |

## Come misuriamo "il migliore"

| Asse | Obiettivo |
| --- | --- |
| Fedeltà | EMD del cycle time e distanza dei percorsi su held-out; battere la baseline SIMOD |
| Trasparenza | 100% run spiegati; ≥ 80% parametri con fonte diversa da Manual |
| Rigore | ogni Δ con intervallo; riproducibilità 100% con stesso seed e revisione |
| Velocità | what-if < 60 s (10 repliche × 1.000 casi); twin da log < 10 min |
| Semplicità | primo insight < 5 min senza configurazione manuale |
| Impatto | errore Δ previsto contro Δ osservato |

Nessuno di questi numeri è ancora misurato in modo ripetibile.

## Dataset di valutazione

`C:\Users\sohay\Desktop\eval simulatore` (fuori dal repo, si passa con una
variabile d'ambiente): dati del paper Chapela-Campa e Dumas sui ritardi estranei
all'attività.

- `inputs/synthetic`: Insurance Claims, Loan Application, Pharmacy, Procure to Pay,
  ciascuno con 0, 1, 3, 5 timer. BPMN, scenario Prosimos e log: la verità è nota,
  quindi misura la qualità della discovery.
- `inputs/real-life`: AcademicCredentials, BPIC 2012 W, BPIC 2017 W. Scenari
  scoperti da SIMOD, log con split train/test.
- `outputs/`: log simulati e `metrics.txt` del paper. Sono la baseline da battere.

## Problemi di produzione aperti

1. `scripts/dev.ps1` avvia Prosimos 1.2.6 (`prosimos-api`), la prod il runner 2.1.0.
   La 1.2.6 ignora in silenzio `branch_rules` ed `event_attributes`.
2. `_process_event_log` in `backend/simulation/service.py` ingoia le eccezioni senza
   log: un run può risultare `completed` senza KPI. Lo stesso per il download del log
   nell'adapter.
3. Il log si scarica con una seconda chiamata HTTP: con più repliche del runner può
   finire su un altro container.
4. Il runner non ha autenticazione, limite sul body né timeout per run.
5. In `execute_claimed_run` gli errori dopo il motore (`sla_outcome`,
   `complete_simulation_run`) sono fuori dal `try`.
6. L'import di scenari Prosimos JSON esiste solo nel frontend ed è rigido: rifiuta i
   metadati degli scenari SIMOD (`process_model`, `model_type`, `granule_size`).
7. Test vitest instabili sotto carico: `shareIsolation`, `CaseRules.ui`.

## Coda di lavoro

Un branch per blocco, commit piccoli, test, merge su `main`, push. Ogni blocco
aggiorna la tabella di stato qui sopra.

| Blocco | Branch | Contenuto |
| --- | --- | --- |
| B0 | `fix/sim-engine-parity` | dev sul runner 2.1.0; adapter esige `EngineVersion` ≥ 2; log restituito inline; errori loggati, run senza KPI marcato; protezioni del runner (problemi 1–5) |
| B1 | `feat/sim-prosimos-import` | import Prosimos JSON tollerante, anche lato server; test sui 19 scenari del dataset eval (problema 6) |
| B2 | `feat/sim-eval-harness` | harness `DELIR_SIM_EVAL_DIR`: run replicati, metriche W1, NGD, RED/CED/CAR, throughput; baseline salvata e confronto con il paper (SIM-19, SIM-36) |
| B3 | `feat/sim-discovery-core` | SIM-16: arrivi, durate per attività con scelta della distribuzione, probabilità dei gateway, risorse e calendari come candidati con fit e alternative (G3) |
| B4 | `feat/sim-discovery-ui` | checklist del digital twin (SIM-18) con approva/modifica/rifiuta, e2e |
| B5 | `feat/sim-extraneous-delays` | scoperta dei ritardi estranei, misurata sul set sintetico contro il paper |
| B6 | `spike/sim-throughput` | G2: run al minuto, prerequisito di SIM-26 |
| B7 | `feat/sim-optimization` | SIM-26: ricerca multi-fedeltà (Erlang-C → Prosimos breve → repliche), frontiera Pareto |
| B8 | `feat/sim-recalibration` | SIM-29: drift e ricalibrazione su log nuovi |

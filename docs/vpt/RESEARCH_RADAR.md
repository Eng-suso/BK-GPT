# Research Radar del VPT

Aggiornato: 2026-11-25. Decisione di Sohayb: servono più dati per costruire il miglior
simulatore e predittore; tutti i dataset e i repository qui sotto si usano per la ricerca
(il prodotto non è ancora in vendita). Il catalogo macchina è
[`../../datasets/manifest.json`](../../datasets/manifest.json), voci con
`"collection": "radar"`; i punti del piano che li usano sono in [`PLAN.md`](./PLAN.md),
sezione «R — Research Radar».

```bash
uv run python scripts/fetch_datasets.py fetch --collection radar   # tutto il radar: ~2,9 GB di download, ~24 GB estratti (bpic-ocel2 da solo 18 GB)
uv run python scripts/fetch_datasets.py fetch bpic2019 simbank      # per id
```

## Regole

1. **Collezione separata.** Il radar non è sviluppo né holdout. I 6 holdout di PROTO-01
   restano congelati e chiusi. Un log del radar entra in un esperimento solo dopo che
   PROTO-02 lo ha dichiarato (sviluppo, nuovo holdout o escluso) in `PROTOCOL.md`.
2. **Deduplica prima dell'uso (RAD-01).** Alcuni pacchetti contengono log che abbiamo già
   (BPIC 2012/2017 dentro ProCause, BPIC 2012 W e BPIC 2013 nella copia di Helpdesk, i log di Camargo dentro i pacchetti di SIMOD, AgentSimulator
   e del BPS Quality Framework). Si confrontano per hash e per nome; un file che coincide con
   un holdout si marca e non si apre. Esclusi già dal manifest: i BPIC 2015 del pacchetto OCEL
   (Municipality 1 è un holdout, gli altri comuni sono lo stesso processo).
3. **Repo pubblico.** Si usano tutti i dati per la ricerca, ma nel repo entra solo ciò che si
   può ripubblicare (CC BY 4.0, Apache-2.0, CC0): il resto sta nella cache di `fetch_datasets`.
   La licenza resta scritta nel manifest perché serve a LIC-01 e al giorno della vendita.
4. **Codice esterno solo nell'ambiente di ricerca**, mai importato dal prodotto finché LIC-01
   non lo ammette (AGPL e GPL compresi: POWL, generatore Declare).

## Cosa manca e cosa lo copre

I 20 sintetici di sviluppo vengono da 4 famiglie di processi: più varianti dello stesso
processo non sono processi indipendenti.

| Capacità | Copertura prima del radar | Dati del radar | Punto del piano |
| --- | --- | --- | --- |
| Fedeltà della simulazione | buona | `bps-quality-framework` | G3b, RAD-02 |
| Generalizzazione cross-industry | limitata | `bpic2019`, `bpic2018`, `helpdesk`, `sepsis-cases`, `hospital-billing`, `road-traffic-fines` | RAD-02 |
| Arrivi non stazionari | limitata | `at-kde` (20 processi), `road-traffic-fines`, `bpic2018` | B3.1 |
| Cause delle attese | parziale | `kronos-waiting-time`, GT-01 | B3.2 |
| Comportamento delle risorse | parziale | `agentsimulator`, `prosit` | B3.4 |
| Decisioni dipendenti dal caso | assente | `das-rp`, `prosit` | B3.3, B3.4 |
| Correttezza del control flow | VAL-01 all'import | `powl`, `declare-log-generator` | B3.3, CONF-03 |
| Validazione controfattuale | da sviluppare | `simbank`, `procause`, `bpic2017-full`, GT-01 | CF-01 |
| Drift e ricalibrazione | da sviluppare | `existential-drifts`, `cdrift-set`, `cdlg-drift-val`, `cdrift-evaluation`, `prosit` | DRIFT-01, B8 |
| Quantificazione dell'incertezza | da sviluppare | GT-01 (parametri nascosti noti) | VPT-01/02 |
| Object-centric | da sviluppare | 7 voci `ocel-*` e `bpic-ocel2`, `simoc` | VPT-07, OC-01 |
| Verità matematica del motore | assente | `queuesim`, `simpy`, `salabim` | ANA-01, ENG-02 |
| Scalabilità | misurata in parte | `bpic2019` (1,6 M eventi), `bpic2018`, `bpic-ocel2` | PERF-01 |

## Dataset

| Id | Cosa contiene | Licenza | Serve a |
| --- | --- | --- | --- |
| `bps-quality-framework` | log originali, modelli BPS, log simulati e misure del framework di qualità (Zenodo 12126071) | Apache-2.0 | fedeltà multidimensionale, confronto delle metriche di B2 |
| `simbank` | simulatore di un processo di credito con interventi e confondenti | CC BY 4.0 | CF-01, B7 |
| `procause` | codice e dati degli esperimenti controfattuali (SimBank, BPIC 2012, 2017) | MIT | CF-01 |
| `bpic2019` | procure-to-pay, ~60 società, 251.734 righe d'ordine, 1,6 M eventi (729 MB XES) | CC BY 4.0 | PERF-01, RAD-02, demo di prodotto |
| `bpic2018` | contributi agricoli UE, tre anni | CC0 | B8, VPT-10, PERF-01 |
| `bpic2017-full` | prestiti, log completo (stessa banca di BPIC 2012) | 4TU | CF-01 con ProCause; non indipendente |
| `sepsis-cases` | percorsi di pazienti con sepsi | 4TU | RAD-02, osservabilità parziale |
| `hospital-billing` | fatturazione ospedaliera | 4TU | RAD-02 |
| `road-traffic-fines` | multe stradali su oltre 10 anni | 4TU | B3.1, B3.2 (scadenze di legge) |
| `helpdesk` | ticket di assistenza (copia CSV di ProcessSequencePrediction) | nessuna | RAD-02 |
| `ocel-container-logistics` | logistica dei container, OCEL 2.0 | CC BY 4.0 | VPT-07, OC-01 |
| `ocel-order-management` | gestione ordini, OCEL 2.0 | CC BY 4.0 | VPT-07, OC-01 |
| `ocel-procure-to-pay` | P2P, OCEL 2.0 | CC BY 4.0 | VPT-07, confronto con BPIC 2019 |
| `ocel-steel-logistics` | logistica reale anonimizzata di un'acciaieria (pubblicato il 2026-11-24) | CC BY 4.0 | VPT-07 su dati reali |
| `ocel-state-aware` | inventory e manufacturing-maintenance con stato degli oggetti | CC BY 4.0 | VPT-07 |
| `ocel-standard-collection` | 7 OCEL 2.0 (P2P, O2C, transfer order, recruiting, …) | CC BY 4.0 | VPT-07 |
| `ocel-lrms-simulated` | O2C, P2P, hiring, hospital simulati | CC BY 4.0 | OC-01 |
| `bpic-ocel2` | BPIC 2014, 2016, 2017, 2019 in OCEL 2.0 | CC BY 4.0 | VPT-07: stesso log piatto e object-centric |
| `existential-drifts` | log sintetici con drift strutturali noti | CC BY 4.0 | DRIFT-01, B8 |
| `cdrift-set` | set di valutazione del rilevamento di drift | MIT | DRIFT-01 |
| `cdlg-drift-val` | log con drift improvvisi, graduali, ricorrenti generati da CDLG (616 MB) | MIT | DRIFT-01, B8 |

## Repository

Fissati a un commit. Si studiano e si eseguono come baseline o come fonte di dati; non si
copiano nel prodotto.

| Id | Cosa fa | Licenza | Ipotesi da verificare | Si adotta se |
| --- | --- | --- | --- | --- |
| `at-kde` | arrivi su tre scale (trend, settimana, giorno) | Apache-2.0 | batte gli arrivi di SIMOD su CAR e AED | vince B3.1 sulla validazione e poi sul test |
| `kronos-waiting-time` | attese in 5 cause | da verificare | la causa si identifica dal log | ≥ 90% di cause giuste su GT-01 |
| `agentsimulator` | risorse come agenti | MIT | le risorse individuali riducono W1 e RED | vince B3.4 dove G3b mostra che le risorse contano |
| `prosit` | parametri dal contesto, alberi adattivi | MIT | il contesto spiega la varianza delle durate | vince B3.4; per B8 la ricalibrazione incrementale |
| `das-rp` | simulazione data-aware | da verificare | i gateway dipendono dagli attributi del caso | NGD migliore dei gateway probabilistici |
| `powl` | discovery sound per costruzione | AGPL-3.0 | sound senza riparazione a valle | 100% dei modelli supera VAL-01 con NGD ≥ SIMOD |
| `cdrift-evaluation` | valutazione del rilevamento di drift | da verificare | — | è il metro di DRIFT-01 |
| `simoc` | simulazione agent-based da OCEL 2.0 | da verificare | la simulazione object-centric perde meno dell'appiattimento | decisione di VPT-07 |
| `declare-log-generator` | log conformi a modelli Declare | GPL-3.0 | — | fonte di processi flessibili per GT-01 e CONF-03 |
| `simpy`, `salabim` | DES di base | MIT | — | candidati di ENG-02, dopo LIC-01 |
| `queuesim` | code e formule analitiche | Apache-2.0 | — | comparatore indipendente di ANA-01 |

**Non acquisiti dalla sessione cloud** (host non raggiungibile o sorgente non identificata):
il generatore CDLG e Steady-State Detection (GitLab dell'Università di Mannheim), l'originale
di Helpdesk (Mendeley Data), ProcessLog. Al posto di CDLG ci sono i log che ha generato
(`cdlg-drift-val`), al posto di Helpdesk la copia CSV. Per SSD serve l'host
`gitlab.uni-mannheim.de` nell'ambiente oppure il download dal computer di Sohayb.

## DeliR Ground Truth Benchmark (GT-01)

Sui dati reali si vede ciò che è successo, non ciò che sarebbe successo con un'altra decisione.
GT-01 genera aziende sintetiche di cui conosciamo la dinamica: DeliR vede solo l'As-Is, il
To-Be con l'intervento resta nascosto fino alla valutazione.

| Dimensione | Cosa varia |
| --- | --- |
| Arrivi | stazionari, stagionali, trend, picchi improvvisi |
| Risorse | calendari, assenze, competenze, multitasking |
| Control flow | loop, XOR, AND, rework, eccezioni |
| Attese | congestione, batching, priorità, timer esterni |
| Interventi | organico, automazione, capacità, routing |
| Qualità dei dati | eventi mancanti, rumore, censura temporale |
| Dinamica | cambi improvvisi, graduali, ricorrenti |
| Incertezza | parametri nascosti, fonti incomplete e contraddittorie |

Più generatori indipendenti, mai solo il motore di DeliR: un generatore proprio su SimPy,
SimBank, AgentSimulator e il generatore Declare. Se DeliR viene valutato solo su dati prodotti
dal suo stesso motore, il benchmark misura la coerenza, non la verità.

## Correzioni al protocollo (da applicare in PROTO-02, senza toccare il benchmark congelato)

1. **Confronti appaiati.** Gli IC al 95% che non si sovrappongono sono un criterio conservativo,
   non un test sulla differenza. Si aggiunge, dove le repliche sono appaiate (stesso seed, stesso
   log), un test sulla differenza (bootstrap appaiato o Wilcoxon) riportato accanto. Le mete già
   scritte restano valide così come sono.
2. **CF-01 non solo copertura.** Una copertura del 90% si ottiene anche con intervalli enormi e
   inutili. Si misurano anche l'ampiezza dell'intervallo, l'errore puntuale sul Δ KPI e la
   direzione dell'effetto.
3. **Il sintetico non basta per la causalità reale.** CF-01 su GT-01 dimostra la validità sotto
   le ipotesi del generatore; nel mondo reale servono pilot con interventi osservati, misure
   prima e dopo e controllo dei confondenti (PV).

## Scorecard della North Star

Obiettivi, non risultati raggiunti.

| Dimensione | Metrica | Meta |
| --- | --- | --- |
| Predictive accuracy | W1, RED, AED, CED, CAR, NGD su log indipendenti | battere "B = A" e le migliori configurazioni pubblicate comparabili |
| Formal correctness | soundness, deadlock, livelock, terminazione | 100% dei modelli accettati corretti nel perimetro supportato |
| Counterfactual reliability | errore sul Δ KPI, copertura e ampiezza degli intervalli, direzione | prevedere l'effetto delle decisioni, non solo lo stato |
| Computational efficiency | latenza P50/P95, memoria, throughput | da 1.000 a 100.000 casi a parità di fedeltà |
| Technological independence | audit delle dipendenze e della proprietà intellettuale | motore sostituibile, licenze compatibili |

## La tesi

La combinazione di AT-KDE, SIMOD, POWL e AgentSimulator è accessibile anche ai concorrenti.
Il vantaggio sta nell'unire in un'unica tecnologia quattro capacità: **selezione automatica
del modello** (SEL-01), **simulazione causale** sotto assunzioni esplicite (CF-01),
**quantificazione dell'incertezza** (VPT-01/02) e **calibrazione adattiva** (B8, DRIFT-01).
Da Process Intelligence a Verified Process Intelligence, con un benchmark abbastanza rigoroso
da dimostrare la superiorità, se i risultati la confermano.
